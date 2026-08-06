"""
B 超结果解析器
- 卵泡数字段解析（如 "16.4×1  15.8×1" → [{"size": 16.4, "count": 1}, ...]）
- 结果对比评估
"""
import re
import json
from typing import Any, Optional
from loguru import logger


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return round(float(value), 1)
    except (ValueError, TypeError):
        return None


def normalize_follicles(follicles: any) -> list[dict]:
    """卵泡明细归一化: 数值化、同尺寸合并、按大小降序。"""
    if not isinstance(follicles, list):
        return []

    merged: dict[float, int] = {}
    for item in follicles:
        if not isinstance(item, dict):
            continue
        size = _to_float(item.get("size"))
        if size is None:
            continue
        try:
            count = int(item.get("count") or 1)
        except (ValueError, TypeError):
            count = 1
        if count <= 0:
            continue
        merged[size] = merged.get(size, 0) + count

    return [
        {"size": size, "count": count}
        for size, count in sorted(merged.items(), key=lambda x: x[0], reverse=True)
    ]


def _follicle_total(follicles: list[dict]) -> int:
    return sum(int(f.get("count") or 0) for f in follicles)


def compare_follicle_details(
    identified: Any,
    ground_truth: Any,
    opposite_identified: Any | None = None,
) -> dict[str, Any]:
    """卵泡明细尺寸级/数量级差异对比。

    输入先统一经过 normalize_follicles()（一位小数、同尺寸合并、按大小降序）：
    - 完全一致时 match=True，无任何差异项。
    - 真实有、抽取没有的尺寸 → missing。
    - 抽取有、真实没有的尺寸 → extra。
    - 同尺寸数量不同 → count_mismatch（diff = identified_count - truth_count）。
    - missing 中的尺寸出现在对侧抽取结果 → possible_side_swaps（疑似左右串边，
      仅提示，不自动修改结果）。
    """
    id_list = normalize_follicles(identified)
    gt_list = normalize_follicles(ground_truth)
    opp_list = normalize_follicles(opposite_identified)

    id_by_size = {item["size"]: int(item["count"]) for item in id_list}
    gt_by_size = {item["size"]: int(item["count"]) for item in gt_list}
    opp_by_size = {item["size"]: int(item["count"]) for item in opp_list}

    missing: list[dict[str, Any]] = []
    extra: list[dict[str, Any]] = []
    count_mismatch: list[dict[str, Any]] = []

    for size, gt_count in gt_by_size.items():
        id_count = id_by_size.get(size)
        if id_count is None:
            missing.append({"size": size, "count": gt_count})
        elif id_count != gt_count:
            count_mismatch.append({
                "size": size,
                "identified_count": id_count,
                "truth_count": gt_count,
                "diff": id_count - gt_count,
            })

    for size, id_count in id_by_size.items():
        if size not in gt_by_size:
            extra.append({"size": size, "count": id_count})

    possible_side_swaps = [
        {**item, "opposite_count": opp_by_size[item["size"]]}
        for item in missing
        if item["size"] in opp_by_size
    ]

    match = not missing and not extra and not count_mismatch

    summary_parts = []
    for item in missing:
        swap_hint = "（疑似串边）" if item["size"] in opp_by_size else ""
        summary_parts.append(f"缺失 {item['size']:g}×{item['count']}{swap_hint}")
    for item in extra:
        summary_parts.append(f"多余 {item['size']:g}×{item['count']}")
    for item in count_mismatch:
        if item["diff"] > 0:
            summary_parts.append(f"{item['size']:g} 多 {item['diff']}")
        else:
            summary_parts.append(f"{item['size']:g} 少 {-item['diff']}")

    return {
        "match": match,
        "identified": id_list,
        "truth": gt_list,
        "identified_total": sum(id_by_size.values()),
        "truth_total": sum(gt_by_size.values()),
        "missing": missing,
        "extra": extra,
        "count_mismatch": count_mismatch,
        "possible_side_swaps": possible_side_swaps,
        "summary": "；".join(summary_parts),
    }


def normalize_structured_result(structured: any) -> any:
    """
    归一化 LLM 结构化结果:
    - 卵泡明细统一排序/合并
    - 当 total 与明细 count 不一致时, 以明细 count 为准
    """
    if not isinstance(structured, dict):
        return structured

    normalized = dict(structured)
    notes = []

    for side, label in (("right", "右侧"), ("left", "左侧")):
        list_key = f"{side}_follicles"
        total_key = f"{side}_follicle_total"
        follicles = normalize_follicles(normalized.get(list_key))
        normalized[list_key] = follicles

        if follicles:
            detail_total = _follicle_total(follicles)
            original_total = normalized.get(total_key)
            try:
                original_total_int = int(original_total) if original_total is not None else None
            except (ValueError, TypeError):
                original_total_int = None
            if original_total_int != detail_total:
                notes.append(
                    f"{label}卵泡总数与明细不一致: 原total={original_total}, 明细合计={detail_total}, 已按明细修正"
                )
            normalized[total_key] = detail_total

    if notes:
        old_uncertain = str(normalized.get("uncertain_text") or "").strip()
        normalized["uncertain_text"] = "；".join([x for x in [old_uncertain, *notes] if x])

    return normalized


def parse_follicle_string(s: Any) -> list[dict]:
    """
    解析卵泡数字段
    输入: "16.4×1  15.8×1  13.4×1" / "16.4, 15.8*2" / JSON 数组
    输出: [{"size": 16.4, "count": 1}, {"size": 15.8, "count": 1}, ...]
    """
    if s is None:
        return []

    if isinstance(s, list):
        return normalize_follicles(s)

    text = str(s).strip()
    if not text or text.upper() in {"NULL", "N/A", "NA", "-"}:
        return []

    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return normalize_follicles(parsed)
        except json.JSONDecodeError:
            pass

    result = []
    # 支持:
    # - 10x2 / 10×2 / 10*2 / 10 X 2
    # - 10、12.5、13（省略数量时按 1 个）
    # - 逗号、顿号、分号、空格、换行混合分隔
    pattern = r"(\d+(?:\.\d+)?)\s*(?:[xX×﹡*]\s*(\d+))?"
    matches = re.findall(pattern, text)

    for size_str, count_str in matches:
        try:
            count = int(count_str) if count_str else 1
            if count <= 0:
                continue
            result.append({
                "size": float(size_str),
                "count": count,
            })
        except ValueError:
            continue

    return normalize_follicles(result)


def summarize_follicles(follicles: list[dict]) -> str:
    """将结构化卵泡数据转为可读文本"""
    if not follicles:
        return "未见卵泡"
    parts = [f"{f['size']}mm×{f['count']}" for f in follicles]
    total = sum(f["count"] for f in follicles)
    return f"{total}个（{'、'.join(parts)}）"


def evaluate_field(identified: any, ground_truth: any, field_type: str = "number",
                   tolerance: float = 0.0) -> dict:
    """
    单个字段对比评估
    返回: {"match": bool, "identified": ..., "truth": ..., "diff": ...}
    """
    if identified is None and ground_truth is None:
        return {"match": True, "identified": None, "truth": None, "diff": None}
    if identified is None or ground_truth is None:
        return {"match": False, "identified": identified, "truth": ground_truth, "diff": None}

    if field_type == "number":
        try:
            diff = abs(float(identified) - float(ground_truth))
            return {
                "match": diff <= tolerance,
                "identified": identified,
                "truth": ground_truth,
                "diff": round(diff, 2),
            }
        except (ValueError, TypeError):
            return {"match": False, "identified": identified, "truth": ground_truth, "diff": None}

    if field_type == "string":
        match = str(identified).strip() == str(ground_truth).strip()
        return {"match": match, "identified": identified, "truth": ground_truth, "diff": None}

    if field_type == "follicle_total":
        try:
            match = int(identified) == int(ground_truth)
            return {
                "match": match,
                "identified": identified,
                "truth": ground_truth,
                "diff": int(identified) - int(ground_truth) if not match else 0,
            }
        except (ValueError, TypeError):
            return {"match": False, "identified": identified, "truth": ground_truth, "diff": None}

    if field_type == "follicles":
        id_list = normalize_follicles(identified)
        gt_list = normalize_follicles(ground_truth)
        return {
            "match": id_list == gt_list,
            "identified": id_list,
            "truth": gt_list,
            "diff": None if id_list == gt_list else {"identified_count": _follicle_total(id_list), "truth_count": _follicle_total(gt_list)},
        }

    return {"match": str(identified) == str(ground_truth),
            "identified": identified, "truth": ground_truth, "diff": None}


def evaluate_result(identified: dict, ground_truth: dict, include_remark: bool = False) -> dict:
    """
    完整评估：对比识别结果与真实结果
    返回每个字段的对比详情与整体准确率
    """
    evaluation = {
        "fields": {},
        "total_fields": 0,
        "correct_fields": 0,
        "accuracy": 0.0,
    }

    field_configs = [
        ("right_follicle_total", "right_follicle_total", "follicle_total", 0),
        ("left_follicle_total", "left_follicle_total", "follicle_total", 0),
        ("right_follicles", "right_follicles", "follicles", 0),
        ("left_follicles", "left_follicles", "follicles", 0),
        ("endometrium_thickness", "endometrium_thickness", "number", 0.5),
        ("endometrium_type", "endometrium_type", "string", 0),
        ("right_ovary_length", "right_ovary_length", "number", 2.0),
        ("right_ovary_width", "right_ovary_width", "number", 2.0),
        ("left_ovary_length", "left_ovary_length", "number", 2.0),
        ("left_ovary_width", "left_ovary_width", "number", 2.0),
    ]
    if include_remark:
        field_configs.append(("remark", "remark", "string", 0))

    correct = 0
    total = 0

    for id_field, gt_field, ftype, tol in field_configs:
        id_val = identified.get(id_field)
        gt_val = ground_truth.get(gt_field)
        result = evaluate_field(id_val, gt_val, ftype, tol)
        evaluation["fields"][id_field] = result
        total += 1
        if result["match"]:
            correct += 1

    evaluation["total_fields"] = total
    evaluation["correct_fields"] = correct
    evaluation["accuracy"] = round(correct / total, 4) if total > 0 else 0.0
    evaluation["include_remark"] = include_remark

    return evaluation


# 默认 LLM 提示词模板
DEFAULT_PROMPT_TEMPLATE = """你是一名辅助生殖超声检查专家。请从以下 B 超检查的语音转写文本中提取关键信息，并以 JSON 格式返回。

## 需要提取的字段

- right_follicle_total: 右侧卵泡总数（整数）
- left_follicle_total: 左侧卵泡总数（整数）
- right_follicles: 右侧卵泡详细列表，每项包含 size（尺寸，mm）和 count（数量）
- left_follicles: 左侧卵泡详细列表
- endometrium_thickness: 内膜厚度（mm，数值）
- endometrium_type: 内膜类型（A/B/C/A-B 等）
- right_ovary_length: 右卵巢长度（mm）
- right_ovary_width: 右卵巢宽度（mm）
- left_ovary_length: 左卵巢长度（mm）
- left_ovary_width: 左卵巢宽度（mm）
- summary: 自然语言总结

## 转写文本

{transcript}

## 返回格式

请只返回 JSON，不要有其他内容：
{{
  "right_follicle_total": 0,
  "left_follicle_total": 0,
  "right_follicles": [],
  "left_follicles": [],
  "endometrium_thickness": 0,
  "endometrium_type": "",
  "right_ovary_length": 0,
  "right_ovary_width": 0,
  "left_ovary_length": 0,
  "left_ovary_width": 0,
  "summary": ""
}}
"""

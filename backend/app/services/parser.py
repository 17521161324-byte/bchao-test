"""
B 超结果解析器
- 卵泡数字段解析（如 "16.4×1  15.8×1" → [{"size": 16.4, "count": 1}, ...]）
- 结果对比评估
"""
import re
from loguru import logger


def parse_follicle_string(s: str) -> list[dict]:
    """
    解析卵泡数字段
    输入: "16.4×1  15.8×1  13.4×1"
    输出: [{"size": 16.4, "count": 1}, {"size": 15.8, "count": 1}, ...]
    """
    if not s or str(s).strip().upper() == "NULL":
        return []

    result = []
    # 匹配 数字×数字 或 数字﹡数字 或 数字*数字 格式
    pattern = r"(\d+\.?\d*)\s*[×﹡*]\s*(\d+)"
    matches = re.findall(pattern, str(s))

    for size_str, count_str in matches:
        try:
            result.append({
                "size": float(size_str),
                "count": int(count_str),
            })
        except ValueError:
            continue

    return result


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

    return {"match": str(identified) == str(ground_truth),
            "identified": identified, "truth": ground_truth, "diff": None}


def evaluate_result(identified: dict, ground_truth: dict) -> dict:
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
        ("endometrium_thickness", "endometrium_thickness", "number", 0.5),
        ("endometrium_type", "endometrium_type", "string", 0),
        ("right_ovary_length", "right_ovary_length", "number", 2.0),
        ("right_ovary_width", "right_ovary_width", "number", 2.0),
        ("left_ovary_length", "left_ovary_length", "number", 2.0),
        ("left_ovary_width", "left_ovary_width", "number", 2.0),
    ]

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

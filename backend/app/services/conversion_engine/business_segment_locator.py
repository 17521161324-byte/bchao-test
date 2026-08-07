"""Rule-based B-ultrasound business segment locator.

This module does not mutate conversion records. It only marks useful spans so
the UI can show which parts of ASR text are being used by extraction rules.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.conversion_engine.context_inference import (
    FUZZY_OVARY_SIZE_TERMS,
    collect_anonymous_ovary_groups,
    collect_fuzzy_ovary_inferences,
    collect_inferred_endometrium_pairs,
)


MEDICAL_TERMS = [
    {
        "field_code": "right_ovary",
        "normalized": "右卵巢",
        "side": "RIGHT",
        # 模糊卵巢大小词不得在词典层直接固定为右侧，统一交给 S006/S011。
        "terms": ["右卵巢大小", "右卵巢", "肉卵巢", "右卵朝"],
    },
    {
        "field_code": "left_ovary",
        "normalized": "左卵巢",
        "side": "LEFT",
        "terms": ["左卵巢大小", "左卵巢", "左卵朝"],
    },
    {
        "field_code": "endometrium",
        "normalized": "内膜",
        "side": None,
        "terms": ["子宫内膜", "内膜", "面膜", "内模"],
    },
]

LOCATOR_WORDS = ["换边", "放边", "另一边", "到左边", "到右边", "左边", "右边", "左侧", "右侧"]
EXPLICIT_SIDE_LOCATORS = {
    "到左边": "LEFT",
    "左边": "LEFT",
    "左侧": "LEFT",
    "到右边": "RIGHT",
    "右边": "RIGHT",
    "右侧": "RIGHT",
}
REMARK_WORDS = [
    "内膜上见多个强回声包块", "内膜中断见息肉体影", "内膜上见强回声包块",
    "连续性稍欠佳", "连续性欠佳", "管状无回声", "囊性无回声",
    "强回声包块", "强回声光团", "息肉样回声", "息肉体影", "宫腔分离", "内膜中断",
    "回声欠均", "回声不均", "稍高回声", "强回声", "无回声", "五回声", "排精",
]
# “五回声 → 无回声”只能由医学词规则决定，不能由 locator 自动决定（避免低风险 AUTO 覆盖高风险 REVIEW）。
REMARK_NORMALIZATION: dict[str, str] = {}
NOISE_WORDS = ["嗯", "啊", "哦", "好", "好的", "可以", "等一下", "我看看"]
ENDOMETRIUM_TYPE_PATTERN = re.compile(r"([ABCＡＢＣ])\s*[型形性]")
DECIMAL_PATTERN = re.compile(r"\d+\.\d+")
SIZE_PATTERN = re.compile(r"(\d{2})\s*[×xX*乘]\s*(\d{2})")
SPLIT_SIZE_PATTERN = re.compile(r"(\d{2})\s*[×xX*乘]\s*(\d)[，,、\s]*(\d{1,2})")
CN_NUM = "零一二三四五六七八九十两幺"
CN_DECIMAL_PATTERN = re.compile(rf"[{CN_NUM}]+点[{CN_NUM}]+")
CN_SIZE_PATTERN = re.compile(rf"([{CN_NUM}]{{2,4}})乘以?([{CN_NUM}]{{2,4}})")
CN_SPLIT_SIZE_PATTERN = re.compile(rf"([{CN_NUM}]{{2,4}})乘以?([{CN_NUM}])([，,、\s]+)([{CN_NUM}]{{1,4}})")


def locate_business_segments(text: str) -> list[dict[str, Any]]:
    """Locate business spans in ASR text.

    Segment types are intentionally limited to four UI-facing categories:
    medical_term, locator, medical_data, noise.

    Detailed business meaning is preserved in field_code:
    endometrium_thickness/endometrium_type, left/right_ovary_size,
    left/right_follicles, remark.
    """
    if not text:
        return []

    segments: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []

    def add(
        segment_type: str,
        start: int,
        end: int,
        *,
        field_code: str = "",
        side: str = "",
        normalized: Any = None,
        participates: bool = True,
        note: str = "",
        rule_id: str = "",
        action: str = "",
        evidence: str = "",
    ):
        if start < 0 or end <= start:
            return
        segments.append({
            "segment_type": segment_type,
            "field_code": field_code,
            "side": side,
            "text": text[start:end],
            "normalized": normalized if normalized is not None else text[start:end],
            "start": start,
            "end": end,
            "participates": participates,
            "note": note,
            "rule_id": rule_id,
            "action": action,
            "evidence": evidence,
        })
        if segment_type not in ("noise",):
            occupied.append((start, end))

    for anchor in _collect_medical_anchors(text):
        add(
            "medical_term",
            anchor["start"],
            anchor["end"],
            field_code=anchor["field_code"],
            side=anchor["side"] or "",
            normalized=anchor["normalized"],
            note="明确医学名词",
        )

    # C006/C007 -> S006/S011：近似词先是UNKNOWN候选，再由全文上下文推断侧别。
    for inferred in collect_fuzzy_ovary_inferences(text):
        field_code = inferred.target_field or "ovary_size_candidate"
        normalized = (
            "右卵巢大小" if inferred.side == "RIGHT" else
            "左卵巢大小" if inferred.side == "LEFT" else
            "卵巢大小"
        )
        add(
            "medical_term", inferred.start, inferred.end,
            field_code=field_code, side=inferred.side, normalized=normalized,
            note=f"{inferred.rule_id} 上下文组合判定：{inferred.evidence}；状态REVIEW",
            rule_id=inferred.rule_id, action=inferred.action, evidence=inferred.evidence,
        )

    # S010：后文首次明确一侧时，把前面的匿名尺寸+连续卵泡组归到另一侧。
    for group in collect_anonymous_ovary_groups(text):
        add(
            "locator", group.start, min(group.end, group.start + len(group.size_text)),
            field_code="inferred_right_segment" if group.side == "RIGHT" else "inferred_left_segment",
            side=group.side, normalized="右卵巢段" if group.side == "RIGHT" else "左卵巢段",
            note=f"S010 上下文反推：{group.evidence}；状态REVIEW",
            rule_id=group.rule_id, action=group.action, evidence=group.evidence,
        )

    for word in LOCATOR_WORDS:
        for m in re.finditer(re.escape(word), text):
            normalized = "换边" if word in ("换边", "放边", "另一边") else word
            add("locator", m.start(), m.end(), field_code="side_switch", normalized=normalized, note="左右归属定位词")

    _locate_endometrium_values(text, add)
    _locate_inferred_endometrium_values(text, add)
    _locate_ovary_sizes_and_follicles(text, add)

    for word in REMARK_WORDS:
        for m in re.finditer(re.escape(word), text):
            add("medical_data", m.start(), m.end(), field_code="remark", normalized=REMARK_NORMALIZATION.get(word, word), note="全局备注候选")

    for word in NOISE_WORDS:
        for m in re.finditer(re.escape(word), text):
            if _overlaps(m.start(), m.end(), occupied):
                continue
            add("noise", m.start(), m.end(), field_code="noise", normalized=word, participates=False, note="口语/噪声，不参与抽取")

    return sorted(_dedupe_segments(segments), key=lambda item: (item["start"], item["end"], item["segment_type"]))


def _locate_endometrium_values(text: str, add):
    anchors = [item for item in _collect_medical_anchors(text) if item["field_code"] == "endometrium"]
    for anchor in anchors:
        window_start = anchor["end"]
        window_end = min(len(text), window_start + 24)
        window = _before_strong_boundary(text[window_start:window_end])
        num = _first_decimal_match(window)
        if num:
            start = window_start + num["start"]
            end = window_start + num["end"]
            add(
                "medical_data",
                start,
                end,
                field_code="endometrium_thickness",
                normalized=num["value"],
                note="内膜定位词后首个小数",
            )
        typ = ENDOMETRIUM_TYPE_PATTERN.search(window)
        if typ:
            start = window_start + typ.start()
            end = window_start + typ.end()
            raw = text[start:end]
            type_char = raw[0].translate(str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C"}))
            add(
                "medical_data",
                start,
                end,
                field_code="endometrium_type",
                normalized=f"{type_char}型",
                note="标准内膜类型仅允许A/B/C型",
            )


def _locate_inferred_endometrium_values(text: str, add):
    for item in collect_inferred_endometrium_pairs(text):
        # 不改写原文；在业务片段中直接标记厚度/类型来源。
        decimal = re.search(r"\d{1,2}\.\d", item.raw_text)
        typ = re.search(r"[ABCＡＢＣ]\s*[型形性]", item.raw_text)
        if decimal:
            add(
                "medical_data", item.start + decimal.start(), item.start + decimal.end(),
                field_code="endometrium_thickness", normalized=item.thickness,
                note=f"S012 反推内膜段：{item.evidence}",
                rule_id=item.rule_id, action=item.action, evidence=item.evidence,
            )
        if typ:
            add(
                "medical_data", item.start + typ.start(), item.start + typ.end(),
                field_code="endometrium_type", normalized=item.endometrium_type,
                note=f"S012 反推内膜段：{item.evidence}",
                rule_id=item.rule_id, action=item.action, evidence=item.evidence,
            )


def _before_strong_boundary(text: str) -> str:
    """Keep value matching in the same utterance chunk.

    Commas are allowed because reports often say "内膜6.3，A型". Strong
    sentence boundaries mean the next number likely belongs to another field,
    e.g. "内膜。十六点八" should not become endometrium thickness.
    """
    match = re.search(r"[。！？?!\n]", text)
    return text[:match.start()] if match else text


def _locate_ovary_sizes_and_follicles(text: str, add):
    anchors = _collect_side_anchors(text)

    for idx, (anchor_start, anchor_end, side) in enumerate(anchors):
        next_anchor = anchors[idx + 1][0] if idx + 1 < len(anchors) else None
        section_end = next_anchor if next_anchor is not None else min(len(text), anchor_end + 240)
        section = text[anchor_end:section_end]
        field_code = "right_ovary_size" if side == "RIGHT" else "left_ovary_size"

        split = _first_size_match(section, split_only=True)
        regular = _first_size_match(section, split_only=False)
        size_match = split or regular
        size_end_abs = anchor_end
        if size_match:
            start = anchor_end + size_match["start"]
            end = anchor_end + size_match["end"]
            if split:
                normalized = f"{split['first']}×{split['second']}"
                note = "卵巢大小窗口内 A×B,C 合并为 A×C/BC"
            else:
                normalized = f"{regular['first']}×{regular['second']}"
                note = "卵巢大小整数尺寸"
            size_end_abs = end
            add("medical_data", start, end, field_code=field_code, side=side, normalized=normalized, note=note)

        follicle_field = "right_follicles" if side == "RIGHT" else "left_follicles"
        follicle_start = size_end_abs
        for num in _iter_decimal_matches(text[follicle_start:section_end]):
            start = follicle_start + num["start"]
            end = follicle_start + num["end"]
            value = num["value"]
            if 2 <= value <= 40:
                add("medical_data", start, end, field_code=follicle_field, side=side, normalized=value, note="当前侧别下卵泡数值")


def _overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < other_end and end > other_start for other_start, other_end in ranges)


def _collect_medical_anchors(text: str) -> list[dict[str, Any]]:
    candidates = []
    for group in MEDICAL_TERMS:
        for word in group["terms"]:
            for m in re.finditer(re.escape(word), text):
                candidates.append({
                    "start": m.start(),
                    "end": m.end(),
                    "field_code": group["field_code"],
                    "text": word,
                    "normalized": group["normalized"],
                    "side": group["side"],
                })
    candidates.sort(key=lambda item: (item["start"], -(item["end"] - item["start"])))

    result: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for item in candidates:
        start, end = item["start"], item["end"]
        if _overlaps(start, end, occupied):
            continue
        occupied.append((start, end))
        result.append(item)
    return sorted(result, key=lambda item: (item["start"], item["end"]))


def _collect_side_anchors(text: str) -> list[tuple[int, int, str]]:
    """Collect anchors that can define the side for ovary values.

    Besides explicit ovary terms, clinicians often say only "右边/左边" and
    immediately start reporting ovary size and follicle values. Those explicit
    side locators should therefore anchor the following ovary data section.
    Vague locators such as "这边/那边" are intentionally excluded.
    """
    candidates: list[tuple[int, int, str, int]] = []

    for item in _collect_medical_anchors(text):
        if item["side"] in ("LEFT", "RIGHT"):
            candidates.append((item["start"], item["end"], item["side"], 2))

    for word, side in EXPLICIT_SIDE_LOCATORS.items():
        for m in re.finditer(re.escape(word), text):
            candidates.append((m.start(), m.end(), side, 1))

    # 近似卵巢大小候选的左右只来自组合规则，优先级低于原文明示侧别。
    for inferred in collect_fuzzy_ovary_inferences(text):
        if inferred.side in ("LEFT", "RIGHT"):
            candidates.append((inferred.start, inferred.end, inferred.side, 1))

    # 匿名测量组用尺寸起点作为虚拟侧别锚点，让后续尺寸/卵泡进入同一业务段。
    for group in collect_anonymous_ovary_groups(text):
        candidates.append((group.start, group.start, group.side, 1))

    candidates.sort(key=lambda item: (item[0], -item[3], -(item[1] - item[0])))
    result: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for start, end, side, _priority in candidates:
        if _overlaps(start, end, occupied):
            continue
        # If an explicit side locator is immediately followed by a same-side
        # ovary term, keep the ovary term as the stronger business anchor.
        if result and result[-1][2] == side and start - result[-1][1] <= 2:
            prev_start, prev_end, prev_side = result[-1]
            if end - start > prev_end - prev_start:
                result[-1] = (start, end, side)
            continue
        occupied.append((start, end))
        result.append((start, end, side))

    return sorted(result, key=lambda item: (item[0], item[1]))


def _first_decimal_match(text: str) -> dict[str, Any] | None:
    matches = list(_iter_decimal_matches(text))
    if not matches:
        return None
    return sorted(matches, key=lambda item: item["start"])[0]


def _iter_decimal_matches(text: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for m in DECIMAL_PATTERN.finditer(text):
        matches.append({"start": m.start(), "end": m.end(), "value": float(m.group())})
    for m in CN_DECIMAL_PATTERN.finditer(text):
        value = _parse_chinese_decimal(m.group())
        if value is not None:
            matches.append({"start": m.start(), "end": m.end(), "value": value})
    return sorted(matches, key=lambda item: item["start"])


def _first_size_match(text: str, *, split_only: bool) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    if split_only:
        for m in SPLIT_SIZE_PATTERN.finditer(text):
            third = int(m.group(3))
            second = third if third >= 10 else int(f"{m.group(2)}{m.group(3)}")
            matches.append({"start": m.start(), "end": m.end(), "first": int(m.group(1)), "second": second})
        for m in CN_SPLIT_SIZE_PATTERN.finditer(text):
            first = _parse_chinese_integer(m.group(1))
            second_head = _parse_chinese_integer(m.group(2))
            third = _parse_chinese_integer(m.group(4))
            if first is None or second_head is None or third is None:
                continue
            second = third if third >= 10 else int(f"{second_head}{third}")
            matches.append({"start": m.start(), "end": m.end(), "first": first, "second": second})
    else:
        for m in SIZE_PATTERN.finditer(text):
            matches.append({"start": m.start(), "end": m.end(), "first": int(m.group(1)), "second": int(m.group(2))})
        for m in CN_SIZE_PATTERN.finditer(text):
            second_raw = m.group(2)
            end = m.end()
            # “五八乘以三八五回声”实际为“58×38 + 无回声”，
            # 最后的“五”属于“五回声”，不能拼进卵巢大小。
            if second_raw.endswith("五") and text[m.end():].startswith("回声") and len(second_raw) > 2:
                second_raw = second_raw[:-1]
                end -= 1
            first = _parse_chinese_integer(m.group(1))
            second = _parse_chinese_integer(second_raw)
            if first is not None and second is not None:
                matches.append({"start": m.start(), "end": end, "first": first, "second": second})
    return sorted(matches, key=lambda item: item["start"])[0] if matches else None


def _parse_chinese_decimal(text: str) -> float | None:
    if "点" not in text:
        return None
    left, right = text.split("点", 1)
    left_num = _parse_chinese_integer(left)
    right_digits = _parse_chinese_digits(right)
    if left_num is None or right_digits == "":
        return None
    return float(f"{left_num}.{right_digits}")


def _parse_chinese_integer(text: str) -> int | None:
    if not text:
        return None
    digit_map = {"零": 0, "一": 1, "幺": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if "十" in text:
        left, _, right = text.partition("十")
        tens = 1 if left == "" else digit_map.get(left)
        ones = 0 if right == "" else digit_map.get(right)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    digits = _parse_chinese_digits(text)
    return int(digits) if digits != "" else None


def _parse_chinese_digits(text: str) -> str:
    digit_map = {"零": "0", "一": "1", "幺": "1", "二": "2", "两": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
    chars = []
    for char in text:
        if char not in digit_map:
            return ""
        chars.append(digit_map[char])
    return "".join(chars)


def _dedupe_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in segments:
        key = (item["segment_type"], item["field_code"], item["start"], item["end"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

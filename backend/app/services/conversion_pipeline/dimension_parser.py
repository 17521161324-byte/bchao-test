"""尺寸候选解析器：处理特殊数字口述场景。

对应改造计划 Task 5：
- D001 乘一误识为乘以（四八乘一。四零 → 48×40）
- D002 异常小数尺寸重建（二九.九乘一点二零 → 29×20，REVIEW）
- D003 缺失卵巢维度（宽度零乘以三八 → ??×38，REVIEW）
- 禁止把不确定数字猜成"看起来合理"的数字
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


DIGIT_MAP = {
    "零": "0",
    "一": "1",
    "幺": "1",
    "二": "2",
    "两": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}

CN_DIGITS = "零一二三四五六七八九幺两"


def parse_spoken_digits(text: str) -> str | None:
    if not text:
        return None
    chars: list[str] = []
    for char in text:
        if char not in DIGIT_MAP:
            return None
        chars.append(DIGIT_MAP[char])
    return "".join(chars)


@dataclass
class DimensionCandidate:
    raw: str
    normalized: str | None
    start: int
    end: int
    action: str
    rule_id: str
    warning_code: str = ""
    message: str = ""
    confidence: float | None = None
    metadata: dict = field(default_factory=dict)


# D001：乘一误识为乘以（"四八乘一。四零"）
BROKEN_MULTIPLY_CN = re.compile(
    rf"(?P<left>[{CN_DIGITS}]{{2}})"
    rf"乘一[。.]?"
    rf"(?P<right>[{CN_DIGITS}]{{2}})"
)

# D002：异常小数尺寸重建（"二九.九乘一点二零"）
BROKEN_DECIMAL_DIMENSION_CN = re.compile(
    rf"(?P<left>[{CN_DIGITS}]{{2}})"
    r"[。.]"
    rf"(?P<left_noise>[{CN_DIGITS}])"
    r"乘一[。.点]?"
    rf"(?P<right>[{CN_DIGITS}]{{2}})"
)

# D003：缺失卵巢维度（"宽度零乘以三八"）
MISSING_FIRST_DIMENSION_CN = re.compile(
    r"(?:宽|宽度)"
    rf"[{CN_DIGITS}]*"
    rf"乘以"
    rf"(?P<right>[{CN_DIGITS}]{{2}})"
)

OVARY_CONTEXT_TERMS = ("卵巢大小", "卵巢")
SIDE_CONTEXT_TERMS = ("左边", "右边", "左侧", "右侧", "左卵巢", "右卵巢")


def _window(text: str, start: int, end: int, radius: int = 12) -> str:
    return text[max(0, start - radius): min(len(text), end + radius)]


def _has_ovary_context(text: str, start: int, end: int) -> bool:
    window = _window(text, start, end)
    return any(term in window for term in OVARY_CONTEXT_TERMS)


def _has_side_context(text: str, start: int, end: int) -> bool:
    window = _window(text, start, end)
    return any(term in window for term in SIDE_CONTEXT_TERMS)


def _candidate(
    match: re.Match,
    normalized: str,
    action: str,
    rule_id: str,
    warning_code: str = "",
    message: str = "",
) -> DimensionCandidate:
    return DimensionCandidate(
        raw=match.group(0),
        normalized=normalized,
        start=match.start(),
        end=match.end(),
        action=action,
        rule_id=rule_id,
        warning_code=warning_code,
        message=message,
    )


def parse_dimension_candidates(text: str) -> list[DimensionCandidate]:
    """从文本中解析尺寸候选（D001/D002/D003）。

    规则：
    - D001：明确卵巢上下文 → AUTO；只有左右侧上下文或无上下文 → REVIEW。
    - D002：始终 REVIEW（候选值由两位读数重建，不做其他泛化）。
    - D003：缺失首维 → ??×N，REVIEW。
    - 不生成任何"猜出来的"数值（如 4.8 → 4.3）。
    """
    if not text:
        return []

    candidates: list[DimensionCandidate] = []

    # D002 必须先于 D001 检查（更长的"左XX.XX乘一"模式优先），避免 D001 误吞。
    for match in BROKEN_DECIMAL_DIMENSION_CN.finditer(text):
        left = parse_spoken_digits(match.group("left"))
        right = parse_spoken_digits(match.group("right"))
        if left is None or right is None:
            continue
        normalized = f"{int(left)}×{int(right)}"
        candidates.append(_candidate(
            match,
            normalized,
            "REVIEW",
            "D002",
            warning_code="DIMENSION_DECIMAL_RECONSTRUCTED",
            message="异常小数尺寸重建候选，需人工确认",
        ))

    for match in BROKEN_MULTIPLY_CN.finditer(text):
        left = parse_spoken_digits(match.group("left"))
        right = parse_spoken_digits(match.group("right"))
        if left is None or right is None:
            continue
        normalized = f"{int(left)}×{int(right)}"
        has_ovary = _has_ovary_context(text, match.start(), match.end())
        action = "AUTO" if has_ovary else "REVIEW"
        candidates.append(_candidate(
            match,
            normalized,
            action,
            "D001",
            message="乘一误识为乘以，尺寸归一",
        ))

    for match in MISSING_FIRST_DIMENSION_CN.finditer(text):
        right = parse_spoken_digits(match.group("right"))
        if right is None:
            continue
        candidates.append(_candidate(
            match,
            f"??×{int(right)}",
            "REVIEW",
            "D003",
            warning_code="OVARY_SIZE_VALUE_MISSING",
            message="卵巢尺寸存在无法确认的维度，必须回听或人工确认",
        ))

    # 按出现位置排序，保证候选顺序稳定
    candidates.sort(key=lambda item: (item.start, item.end))
    return candidates

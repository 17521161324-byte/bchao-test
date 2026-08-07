"""B超口述中的上下文组合判定规则。

本模块只负责“候选/片段级推断”，不直接修改 ASR 文本：
- C006/C007 类近似词先生成“卵巢大小候选”，side=UNKNOWN；
- S006/S011 在业务片段阶段根据前后明确侧别做互补侧别判断；
- S010 对“前置匿名测量组 + 后置明确侧别”做反向片段归属；
- S012 对未位于左右卵巢段内的“几点几 + A/B/C型”建立内膜候选段。

所有由上下文推断出的左右侧别均为 REVIEW，不冒充原文明确侧别。
"""
from __future__ import annotations

from dataclasses import dataclass
import re


FUZZY_OVARY_SIZE_TERMS: tuple[str, ...] = (
    "六宛桥大桥",
    "六碗桥大桥",
    "图案朝大小",
    "满朝大赏",
    "输卵管大小",
)

EXPLICIT_OVARY_SIZE_PATTERN = re.compile(r"(?P<side>[左右])卵巢大小")
EXPLICIT_OVARY_PATTERN = re.compile(r"(?P<side>[左右])卵巢(?:大小|内|外)?")
ARABIC_SIZE_PATTERN = re.compile(r"(?<!\d)(?P<a>\d{2})\s*[×xX*]\s*(?P<b>\d{2})(?!\d)")
ARABIC_DECIMAL_PATTERN = re.compile(r"(?<!\d)(?P<value>\d{1,2}\.\d)(?!\d)")
ENDOMETRIUM_PAIR_PATTERN = re.compile(
    r"(?<!\d)(?P<value>\d{1,2}\.\d)(?!\d)"
    r"\s*[，,、:：]?\s*"
    r"(?P<type>[ABCＡＢＣ])\s*[型形性]"
)
# P0-02：无“型”后缀的“几点几 + A/B/C”同样可能是内膜段（如 14.8A），
# 但缺少“型”不能 AUTO，必须 REVIEW。负向断言避免吞掉标准“X型”写法。
ENDOMETRIUM_PAIR_NO_SUFFIX_PATTERN = re.compile(
    r"(?<!\d)(?P<value>\d{1,2}\.\d)(?!\d)"
    r"\s*[，,、:：]?\s*"
    r"(?P<type>[ABCＡＢＣ])(?![型形性])"
)

SIDE_MAP = {"左": "LEFT", "右": "RIGHT"}
OPPOSITE_SIDE = {"LEFT": "RIGHT", "RIGHT": "LEFT"}


@dataclass(frozen=True)
class FuzzyOvaryInference:
    term: str
    start: int
    end: int
    side: str
    target_field: str | None
    evidence: str
    rule_id: str = "S006"
    action: str = "REVIEW"


@dataclass(frozen=True)
class AnonymousOvaryGroup:
    start: int
    end: int
    side: str
    target_field: str
    evidence: str
    size_text: str
    rule_id: str = "S010"
    action: str = "REVIEW"


@dataclass(frozen=True)
class EndometriumInference:
    start: int
    end: int
    thickness: float
    endometrium_type: str
    raw_text: str
    evidence: str
    rule_id: str = "S012"
    action: str = "AUTO"


def _explicit_size_anchors(text: str) -> list[dict]:
    rows: list[dict] = []
    for match in EXPLICIT_OVARY_SIZE_PATTERN.finditer(text):
        rows.append({
            "start": match.start(),
            "end": match.end(),
            "side": SIDE_MAP[match.group("side")],
            "text": match.group(0),
        })
    return rows


def _has_new_measurement_group(text: str, start: int, end_limit: int | None = None) -> bool:
    """候选词后是否形成新的“尺寸 + 卵泡数值组”。

    主要用于 S011：前一测量组侧别已知时，后续重新出现卵巢大小候选，
    必须紧跟新的尺寸/数值组才按另一侧推断，避免仅凭近似词误判。
    """
    limit = min(len(text), end_limit if end_limit is not None else start + 100)
    window = text[start:limit]
    size = ARABIC_SIZE_PATTERN.search(window)
    if not size or size.start() > 36:
        return False
    after_size = window[size.end():]
    decimals = list(ARABIC_DECIMAL_PATTERN.finditer(after_size))
    return len(decimals) >= 1


def collect_fuzzy_ovary_inferences(text: str) -> list[FuzzyOvaryInference]:
    """对所有近似卵巢大小词执行上下文组合侧别判定。"""
    if not text:
        return []

    explicit = _explicit_size_anchors(text)
    candidates: list[tuple[int, int, str]] = []
    for term in FUZZY_OVARY_SIZE_TERMS:
        for match in re.finditer(re.escape(term), text):
            candidates.append((match.start(), match.end(), term))
    candidates.sort()

    results: list[FuzzyOvaryInference] = []
    for start, end, term in candidates:
        previous = [row for row in explicit if row["end"] <= start]
        following = [row for row in explicit if row["start"] >= end]
        previous_anchor = previous[-1] if previous else None
        following_anchor = following[0] if following else None

        inferred_from_previous: str | None = None
        inferred_from_following: str | None = None
        evidence_parts: list[str] = []

        # S011：前一完整卵巢大小段已明确，当前候选后形成新的测量组 → 另一侧。
        if previous_anchor:
            next_boundary = following_anchor["start"] if following_anchor else None
            if _has_new_measurement_group(text, end, next_boundary):
                inferred_from_previous = OPPOSITE_SIDE[previous_anchor["side"]]
                evidence_parts.append(
                    f"前文已明确{previous_anchor['text']}，本处候选后出现新的尺寸/卵泡测量组"
                )

        # S006：候选在明确的另一侧卵巢大小之前，且中间无同侧明确大小锚点 → 互补侧。
        if following_anchor:
            conflicting = [
                row for row in explicit
                if end <= row["start"] < following_anchor["start"]
                and row["side"] != following_anchor["side"]
            ]
            if not conflicting:
                inferred_from_following = OPPOSITE_SIDE[following_anchor["side"]]
                evidence_parts.append(
                    f"后文明确{following_anchor['text']}，前置卵巢大小候选按双侧互补关系判断"
                )

        sides = {side for side in (inferred_from_previous, inferred_from_following) if side}
        if len(sides) == 1:
            side = sides.pop()
            target_field = "right_ovary_size" if side == "RIGHT" else "left_ovary_size"
            # 诊断保持单一可追踪规则ID：只要前文已知侧别参与判定，
            # 归入 S011；否则为 S006。证据字段仍保留前后文全部依据。
            rule_id = "S011" if inferred_from_previous else "S006"
        else:
            side = "UNKNOWN"
            target_field = None
            if len(sides) > 1:
                evidence_parts.append("前后上下文给出冲突侧别，保持UNKNOWN")
            elif not evidence_parts:
                evidence_parts.append("缺少可完成互补侧别判断的明确上下文")
            rule_id = "S006"

        results.append(FuzzyOvaryInference(
            term=term,
            start=start,
            end=end,
            side=side,
            target_field=target_field,
            evidence="；".join(evidence_parts),
            rule_id=rule_id,
        ))
    return results


def collect_anonymous_ovary_groups(text: str) -> list[AnonymousOvaryGroup]:
    """识别“前置匿名测量组 + 后置明确另一侧”的业务片段。

    当前规则优先解决真实口述中的典型结构：内膜数据之后先报一组卵巢尺寸/卵泡，
    随后才明确说“左卵巢大小/右卵巢大小”。前一组可作为另一侧候选段。
    """
    if not text:
        return []

    explicit = _explicit_size_anchors(text)
    if not explicit:
        return []

    groups: list[AnonymousOvaryGroup] = []
    first_anchor = explicit[0]
    prefix = text[:first_anchor["start"]]

    # 若前面已有明确卵巢锚点，则不把它当匿名组。
    prior_explicit_ovary = list(EXPLICIT_OVARY_PATTERN.finditer(prefix))
    if prior_explicit_ovary:
        return []

    # 取明确侧别前最靠前的二维尺寸，并要求其后至少存在两个疑似卵泡小数。
    for size in ARABIC_SIZE_PATTERN.finditer(prefix):
        decimals = list(ARABIC_DECIMAL_PATTERN.finditer(prefix[size.end():]))
        if len(decimals) < 2:
            continue
        side = OPPOSITE_SIDE[first_anchor["side"]]
        groups.append(AnonymousOvaryGroup(
            start=size.start(),
            end=first_anchor["start"],
            side=side,
            target_field="right_ovary_size" if side == "RIGHT" else "left_ovary_size",
            evidence=(
                f"前置片段存在完整二维尺寸及连续疑似卵泡数值；后文首次明确{first_anchor['text']}，"
                "因此前置匿名测量组按双侧互补关系归到另一侧"
            ),
            size_text=size.group(0),
        ))
        break

    return groups


STRONG_BLOCK_BOUNDARY_PATTERN = re.compile(r"[。！？?!\n；;]")


def _strong_block_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """返回当前强句界内的文本范围。

    业务片段不是简单地“从首次卵巢词到全文结束”。医生可能先报右侧，
    插入一段独立的内膜口述，再继续左侧。因此 S012 按当前强句块判断，
    只要该块本身没有左右卵巢/模糊卵巢大小锚点，就仍允许反推内膜。
    """
    left = 0
    for boundary in STRONG_BLOCK_BOUNDARY_PATTERN.finditer(text, 0, start):
        left = boundary.end()
    right_match = STRONG_BLOCK_BOUNDARY_PATTERN.search(text, end)
    right = right_match.start() if right_match else len(text)
    return left, right


def _infer_endometrium_from_match(
    text: str,
    match: re.Match,
    *,
    action: str,
    missing_type_suffix: bool = False,
) -> EndometriumInference | None:
    """从单个“几点几 + A/B/C(型)”匹配构造 EndometriumInference（共用上下文检查）。

    P0-02：missing_type_suffix=True 时动作为 REVIEW——缺少“型”后缀不能 AUTO，
    只生成“内膜厚度 + 内膜类型候选”，需人工确认。
    """
    block_start, block_end = _strong_block_bounds(text, match.start(), match.end())
    before_in_block = text[block_start:match.start()]

    # 只判断该数值之前是否已进入卵巢段：
    # “7.0A型，右卵巢大小...” 仍应建立内膜段；
    # “右卵巢大小...，7.0A型” 则属于已进入的卵巢段，不反推。
    if EXPLICIT_OVARY_PATTERN.search(before_in_block):
        return None
    if any(term in before_in_block for term in FUZZY_OVARY_SIZE_TERMS):
        return None

    # 若近邻已经明确出现“内膜”，交给正常 F001/F002 处理，不重复生成推断。
    before = text[max(block_start, match.start() - 16):match.start()]
    if "内膜" in before:
        return None

    type_char = match.group("type").translate(str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C"}))
    evidence = (
        "该值所在独立句块不属于左右卵巢段，且满足标准的“内膜厚度小数 + A/B/C型”组合"
    )
    if missing_type_suffix:
        evidence = (
            f"该值所在独立句块不属于左右卵巢段，但类型字母“{match.group('type')}”缺少"
            "“型”后缀（如 14.8A），只能作为内膜厚度+内膜类型候选，需人工确认"
        )
    return EndometriumInference(
        start=match.start(),
        end=match.end(),
        thickness=float(match.group("value")),
        endometrium_type=f"{type_char}型",
        raw_text=match.group(0),
        evidence=evidence,
        action=action,
    )


def collect_inferred_endometrium_pairs(text: str) -> list[EndometriumInference]:
    """在非卵巢业务句块中识别“几点几 + A/B/C型”内膜标准场景。

    P0-02：同时识别缺少“型”后缀的“几点几 + A/B/C”（如 14.8A），
    该情况动作为 REVIEW，只生成候选不自动确认。
    """
    if not text:
        return []

    results: list[EndometriumInference] = []
    for match in ENDOMETRIUM_PAIR_PATTERN.finditer(text):
        inferred = _infer_endometrium_from_match(text, match, action="AUTO")
        if inferred is not None:
            results.append(inferred)

    for match in ENDOMETRIUM_PAIR_NO_SUFFIX_PATTERN.finditer(text):
        # 已有标准“X型”匹配的位置不重复推断（该位置由上一个循环覆盖）。
        if any(r.start == match.start() and r.end == match.end() for r in results):
            continue
        inferred = _infer_endometrium_from_match(
            text, match, action="REVIEW", missing_type_suffix=True,
        )
        if inferred is not None:
            results.append(inferred)
    return results

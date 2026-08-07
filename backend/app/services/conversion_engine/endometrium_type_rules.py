"""Confirmed endometrium-type rules for follicle-monitoring ASR.

The business field ``endometrium_type`` is deliberately strict: only A/B/C.
Other endometrial ultrasound descriptions belong to remark and are handled by
``field_parser``.  This module only identifies explicit type tokens inside an
endometrium window and review-only suspicious/conflicting type evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


TYPE_TRANSLATION = str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C"})
ENDOMETRIUM_ANCHOR_PATTERN = re.compile(r"子宫内膜|内膜")
EXPLICIT_TYPE_PATTERN = re.compile(r"(?P<letter>[ABCＡＢＣ])\s*[型形性]")
SUSPICIOUS_ENDOMETRIUM_TYPE_TERMS = ("飞行", "地形", "黑皮")
# A new core business anchor ends the current endometrium window.  Commas are
# intentionally not boundaries because clinicians commonly say “内膜9.5，C型”.
CORE_OVARY_ANCHOR_PATTERN = re.compile(
    r"左卵巢(?:大小|内|外)?|右卵巢(?:大小|内|外)?|"
    r"六宛桥大桥|六碗桥大桥|图案朝大小|满朝大赏|输卵管大小"
)
STRONG_BOUNDARY_PATTERN = re.compile(r"[。！？?!\n；;]")
MAX_WINDOW_CHARS = 36


@dataclass(frozen=True)
class EndometriumTypeRuleItem:
    rule_id: str
    action: str
    start: int
    end: int
    raw: str
    converted: str | None
    message: str
    evidence: str


def _normalized_type(raw_letter: str) -> str:
    return f"{raw_letter.translate(TYPE_TRANSLATION)}型"


def _window_end(text: str, anchor_end: int) -> int:
    limit = min(len(text), anchor_end + MAX_WINDOW_CHARS)
    ovary = CORE_OVARY_ANCHOR_PATTERN.search(text, anchor_end, limit)
    strong = STRONG_BOUNDARY_PATTERN.search(text, anchor_end, limit)
    candidates = [limit]
    if ovary:
        candidates.append(ovary.start())
    if strong:
        candidates.append(strong.start())
    return min(candidates)


def collect_endometrium_type_rule_items(text: str) -> list[EndometriumTypeRuleItem]:
    """Return M003/M006/M007 rule items for explicit endometrium windows.

    - M003: one explicit A/B/C type in an endometrium window -> AUTO.
    - M006: more than one explicit type in one window -> REVIEW; the last
      complete token is exposed as the candidate value, original text remains.
    - M007: suspicious type-like ASR term inside the window -> REVIEW with no
      guessed A/B/C value.
    """
    if not text:
        return []

    items: list[EndometriumTypeRuleItem] = []
    consumed_until = -1
    for anchor in ENDOMETRIUM_ANCHOR_PATTERN.finditer(text):
        # “子宫内膜” and its inner “内膜” overlap; keep the longer first anchor.
        if anchor.start() < consumed_until:
            continue
        consumed_until = anchor.end()
        end = _window_end(text, anchor.end())
        window = text[anchor.end():end]
        explicit = list(EXPLICIT_TYPE_PATTERN.finditer(window))

        if len(explicit) == 1:
            match = explicit[0]
            start = anchor.end() + match.start()
            finish = anchor.end() + match.end()
            items.append(EndometriumTypeRuleItem(
                rule_id="M003",
                action="AUTO",
                start=start,
                end=finish,
                raw=text[start:finish],
                converted=_normalized_type(match.group("letter")),
                message="标准内膜类型识别",
                evidence="内膜锚点后的同一业务窗口内出现唯一明确A/B/C型",
            ))
        elif len(explicit) > 1:
            # Last complete type is only a review candidate, never a silent text replacement.
            last = explicit[-1]
            start = anchor.end() + last.start()
            finish = anchor.end() + last.end()
            all_raw = "、".join(match.group(0) for match in explicit)
            items.append(EndometriumTypeRuleItem(
                rule_id="M006",
                action="REVIEW",
                start=start,
                end=finish,
                raw=all_raw,
                converted=_normalized_type(last.group("letter")),
                message="同一内膜窗口出现多个类型，需人工确认",
                evidence=f"同一内膜窗口命中多个完整类型：{all_raw}；仅把最后一个完整类型作为候选",
            ))

        for term in SUSPICIOUS_ENDOMETRIUM_TYPE_TERMS:
            for suspicious in re.finditer(re.escape(term), window):
                start = anchor.end() + suspicious.start()
                finish = anchor.end() + suspicious.end()
                items.append(EndometriumTypeRuleItem(
                    rule_id="M007",
                    action="REVIEW",
                    start=start,
                    end=finish,
                    raw=term,
                    converted=None,
                    message="疑似内膜类型近音词，禁止盲猜A/B/C",
                    evidence=f"“{term}”位于内膜业务窗口，但没有足够证据映射到A/B/C型",
                ))

    return sorted(items, key=lambda item: (item.start, item.end, item.rule_id))

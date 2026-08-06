"""文本位置映射：维护 raw/current 双向映射，避免最终靠全文重新搜索。

对应改造计划 Task 4。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpanReplacement:
    raw_start: int
    raw_end: int
    current_start: int
    current_end: int
    raw_text: str
    current_text: str
    rule_id: str


class SpanMap:
    def __init__(self, raw_text: str) -> None:
        self.raw_text = raw_text
        self.replacements: list[SpanReplacement] = []

    def record(
        self,
        *,
        raw_start: int,
        raw_end: int,
        current_start: int,
        current_end: int,
        raw_text: str,
        current_text: str,
        rule_id: str,
    ) -> None:
        self.replacements.append(
            SpanReplacement(
                raw_start=raw_start,
                raw_end=raw_end,
                current_start=current_start,
                current_end=current_end,
                raw_text=raw_text,
                current_text=current_text,
                rule_id=rule_id,
            )
        )

    def current_to_raw(self, start: int, end: int) -> tuple[int, int]:
        exact = [
            item for item in self.replacements
            if item.current_start == start and item.current_end == end
        ]
        if exact:
            item = exact[-1]
            return item.raw_start, item.raw_end
        return start, end

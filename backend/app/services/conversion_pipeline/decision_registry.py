"""决策注册表：防止 REVIEW/BLOCK 被后续低风险 AUTO 覆盖。

对应改造计划 Task 2。同一或重叠原文区间，如果前面已有更高优先级的决策
（BLOCK > REVIEW > CANDIDATE > AUTO > NONE），后续步骤禁止把它降级。
"""
from __future__ import annotations

from dataclasses import asdict

from app.services.conversion_pipeline.types import (
    ACTION_PRECEDENCE,
    RuleDecision,
)


class DecisionRegistry:
    def __init__(self) -> None:
        self._decisions: list[RuleDecision] = []

    @property
    def decisions(self) -> list[RuleDecision]:
        return list(self._decisions)

    def find_overlaps(self, start: int, end: int) -> list[RuleDecision]:
        return [
            item
            for item in self._decisions
            if start < item.end and end > item.start
        ]

    def can_apply(self, candidate: RuleDecision) -> bool:
        overlaps = self.find_overlaps(candidate.start, candidate.end)
        if not overlaps:
            return True

        candidate_weight = ACTION_PRECEDENCE.get(candidate.action, 0)
        highest_existing = max(
            ACTION_PRECEDENCE.get(item.action, 0)
            for item in overlaps
        )
        return candidate_weight >= highest_existing

    def register(self, candidate: RuleDecision) -> bool:
        if not self.can_apply(candidate):
            return False

        overlaps = self.find_overlaps(candidate.start, candidate.end)
        candidate_weight = ACTION_PRECEDENCE.get(candidate.action, 0)

        self._decisions = [
            item
            for item in self._decisions
            if not (
                item in overlaps
                and ACTION_PRECEDENCE.get(item.action, 0) < candidate_weight
            )
        ]
        self._decisions.append(candidate)
        return True

    def to_dicts(self) -> list[dict]:
        return [asdict(item) for item in self._decisions]

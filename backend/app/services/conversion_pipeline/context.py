"""流水线上下文：承载全流程状态。

对应改造计划 Task 3。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.conversion_pipeline.decision_registry import DecisionRegistry
from app.services.conversion_pipeline.types import ParserState, PipelineStepSnapshot


@dataclass
class PipelineContext:
    raw_text: str
    current_text: str
    scene: str
    model_name: str
    conversion_version: str
    config_hash: str
    lexicon_rules: list[dict[str, Any]] = field(default_factory=list)
    runtime_rules: list[dict[str, Any]] = field(default_factory=list)
    parser_state: ParserState = field(default_factory=ParserState)
    decision_registry: DecisionRegistry = field(default_factory=DecisionRegistry)

    conversions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)
    source_spans: list[dict[str, Any]] = field(default_factory=list)
    risk_items: list[dict[str, Any]] = field(default_factory=list)
    steps: list[PipelineStepSnapshot] = field(default_factory=list)

    def append_step(self, snapshot: PipelineStepSnapshot) -> None:
        self.steps.append(snapshot)

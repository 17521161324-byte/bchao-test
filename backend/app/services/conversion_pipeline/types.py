"""流水线核心内部类型。

对应改造计划 Task 1：建立流水线类型（StepCode/STEP_ORDER/ResultLevel/
RuleAction/ACTION_PRECEDENCE/RuleDecision/ParserState/PipelineStepSnapshot/
PipelineRunResult）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepCode(str, Enum):
    BASE_CLEANING = "BASE_CLEANING"
    NUMBER_NORMALIZE = "NUMBER_NORMALIZE"
    MEDICAL_TERM = "MEDICAL_TERM"
    BUSINESS_SEGMENT = "BUSINESS_SEGMENT"
    FIELD_PARSE = "FIELD_PARSE"
    RUNTIME_RULE = "RUNTIME_RULE"
    RISK_INTERCEPT = "RISK_INTERCEPT"


STEP_ORDER: dict[StepCode, int] = {
    StepCode.BASE_CLEANING: 10,
    StepCode.NUMBER_NORMALIZE: 20,
    StepCode.MEDICAL_TERM: 30,
    StepCode.BUSINESS_SEGMENT: 40,
    StepCode.FIELD_PARSE: 50,
    StepCode.RUNTIME_RULE: 60,
    StepCode.RISK_INTERCEPT: 70,
}


STEP_NAMES: dict[StepCode, str] = {
    StepCode.BASE_CLEANING: "基础清洗",
    StepCode.NUMBER_NORMALIZE: "数字与尺寸解析",
    StepCode.MEDICAL_TERM: "医学词处理",
    StepCode.BUSINESS_SEGMENT: "业务片段定位",
    StepCode.FIELD_PARSE: "上下文与字段解析",
    StepCode.RUNTIME_RULE: "参数化规则执行",
    StepCode.RISK_INTERCEPT: "风险校验与分流",
}


class ResultLevel(str, Enum):
    AUTO_ACCEPT = "AUTO_ACCEPT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    MANUAL_AUDIO_REVIEW = "MANUAL_AUDIO_REVIEW"


class RuleAction(str, Enum):
    NONE = "NONE"
    AUTO = "AUTO"
    CANDIDATE = "CANDIDATE"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


ACTION_PRECEDENCE: dict[str, int] = {
    RuleAction.NONE.value: 0,
    RuleAction.AUTO.value: 10,
    RuleAction.CANDIDATE.value: 20,
    RuleAction.REVIEW.value: 30,
    RuleAction.BLOCK.value: 40,
}


@dataclass
class RuleDecision:
    rule_id: str
    rule_version: str
    step_code: str
    action: str
    category: str
    raw: str
    converted: str | None
    start: int
    end: int
    risk_level: str = "low"
    warning_code: str = ""
    message: str = ""
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParserState:
    current_side: str = "UNKNOWN"
    current_field: str | None = None
    current_mode: str = "IDLE"
    ovary_size_complete: dict[str, bool] = field(
        default_factory=lambda: {"LEFT": False, "RIGHT": False}
    )
    locked_fields: set[str] = field(default_factory=set)
    in_remark: bool = False
    last_explicit_side_position: int | None = None
    unassigned_values: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_side": self.current_side,
            "current_field": self.current_field,
            "current_mode": self.current_mode,
            "ovary_size_complete": dict(self.ovary_size_complete),
            "locked_fields": sorted(self.locked_fields),
            "in_remark": self.in_remark,
            "last_explicit_side_position": self.last_explicit_side_position,
            "unassigned_values": list(self.unassigned_values),
        }


@dataclass
class PipelineStepSnapshot:
    step_code: str
    step_name: str
    step_order: int
    status: str
    input_text: str
    output_text: str
    conversions: list[dict[str, Any]] = field(default_factory=list)
    rule_hits: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    state_before: dict[str, Any] = field(default_factory=dict)
    state_after: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)
    source_spans: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    error_message: str | None = None


@dataclass
class PipelineRunResult:
    raw_text: str
    normalized_text: str
    fields: dict[str, Any]
    source_spans: list[dict[str, Any]]
    conversions: list[dict[str, Any]]
    warnings: list[str]
    risk_items: list[dict[str, Any]]
    steps: list[PipelineStepSnapshot]
    result_level: ResultLevel
    risk_passed: bool
    risk_blocked: bool
    config_hash: str

"""流水线 API Schema（Task 14 + P0 扩展）。"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class PipelineExecutionCreate(BaseModel):
    # P1-04：conversion_preview 无实现来源，从 Literal 移除，避免虚假接口能力
    source_type: Literal[
        "manual",
        "text_validation_run",
    ] = "manual"
    source_id: int | None = None
    input_source: Literal[
        "manual",
        "raw_asr_text",
        "corrected_text",
    ] = "manual"
    text: str | None = None

    scene: str = ""
    model_name: str = ""
    rule_version_id: int | None = None
    run_mode: Literal["create_only", "run_all"] = "run_all"

    model_config = {"protected_namespaces": ()}

    @model_validator(mode="after")
    def validate_source(self):
        if self.source_type == "manual" and not (self.text or "").strip():
            raise ValueError("manual source requires text")
        if self.source_type != "manual" and not self.source_id:
            raise ValueError("non-manual source requires source_id")
        return self


class PipelineRunStepRequest(BaseModel):
    step_code: str


class PipelineRunToStepRequest(BaseModel):
    step_code: str


class PipelineRunFromStepRequest(BaseModel):
    step_code: str
    rule_version_id: int | None = None


class PipelineContinueRequest(BaseModel):
    from_step_code: str
    run_mode: Literal["run_all", "run_step"] = "run_all"


class PipelineStepOutputPatch(BaseModel):
    manual_output_text: str
    edit_note: str = ""


class PipelineCompareRequest(BaseModel):
    left_execution_id: int
    right_execution_id: int


class PipelineStepOut(BaseModel):
    id: int | None = None
    step_code: str
    step_name: str
    step_order: int
    status: str
    input_text: str
    output_text: str
    conversions: list[dict[str, Any]] = Field(default_factory=list)
    rule_hits: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)
    state_transitions: list[dict[str, Any]] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)
    source_spans: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0
    config_hash: str = ""
    error_message: str | None = None
    # 步骤输出编辑数据结构
    system_output_text: str | None = None
    manual_output_text: str | None = None
    effective_output_text: str | None = None
    edited: int = 0
    edited_by: str = ""
    edited_at: datetime | None = None
    edit_note: str | None = None

    model_config = {"from_attributes": True}


class PipelineStepPatchOut(BaseModel):
    step: PipelineStepOut
    invalidated_step_codes: list[str] = Field(default_factory=list)


class PipelineExecutionOut(BaseModel):
    id: int
    source_type: str
    source_id: int | None
    input_source: str
    input_text: str
    scene: str
    model_name: str
    rule_version_id: int | None
    rule_version_code: str
    config_hash: str
    parent_execution_id: int | None = None
    fork_step_code: str | None = None
    status: str
    result_level: str | None
    final_text: str
    final_fields: dict[str, Any] = Field(default_factory=dict)
    final_warnings: list[str] = Field(default_factory=list)
    final_risk_items: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[PipelineStepOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}

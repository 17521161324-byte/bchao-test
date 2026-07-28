"""ASR 转化评估 API schema。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConversionRecordCreateFromExam(BaseModel):
    asr_result_id: int | None = None
    converted_text: str | None = None
    conversion_version: str = "manual"


class ConversionRecordUpdate(BaseModel):
    converted_text: str | None = None
    reference_text: str | None = None
    conversion_version: str | None = None
    review_status: str | None = None


class ConversionDetailCreate(BaseModel):
    raw_fragment: str = ""
    converted_fragment: str = ""
    raw_start: int | None = None
    raw_end: int | None = None
    context_before: str = ""
    context_after: str = ""
    action_type: str = "replace"
    category: str = "other"
    rule_id: str | None = None
    rule_version: str | None = None
    confidence: float | None = None
    risk_level: str = "low"
    risk_type: str | None = None
    note: str | None = None


class ConversionDetailUpdate(BaseModel):
    raw_fragment: str | None = None
    converted_fragment: str | None = None
    raw_start: int | None = None
    raw_end: int | None = None
    context_before: str | None = None
    context_after: str | None = None
    action_type: str | None = None
    category: str | None = None
    rule_id: str | None = None
    rule_version: str | None = None
    confidence: float | None = None
    risk_level: str | None = None
    risk_type: str | None = None
    system_judgement: str | None = None
    manual_judgement: str | None = None
    final_judgement: str | None = None
    note: str | None = None


class ConversionReviewCreate(BaseModel):
    detail_id: int | None = None
    review_action: str
    is_high_risk: bool = False
    high_risk_type: str | None = None
    note: str | None = None
    reviewer: str | None = None


class ConversionDetailOut(BaseModel):
    id: int
    record_id: int
    raw_fragment: str = ""
    converted_fragment: str = ""
    raw_start: int | None = None
    raw_end: int | None = None
    context_before: str = ""
    context_after: str = ""
    action_type: str = "replace"
    category: str = "other"
    rule_id: str | None = None
    rule_version: str | None = None
    confidence: float | None = None
    risk_level: str = "low"
    risk_type: str | None = None
    system_judgement: str = "pending"
    manual_judgement: str | None = None
    final_judgement: str = "pending"
    note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ConversionReviewOut(BaseModel):
    id: int
    record_id: int
    detail_id: int | None = None
    review_action: str
    is_high_risk: bool | int = False
    high_risk_type: str | None = None
    note: str | None = None
    reviewer: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ConversionRecordOut(BaseModel):
    id: int
    batch_id: int | None = None
    exam_record_id: int
    asr_result_id: int | None = None
    reference_asr_id: int | None = None
    record_id_snapshot: str | None = None
    date_snapshot: str | None = None
    asr_model_name: str | None = None
    source_config_hash: str | None = None
    raw_text: str = ""
    converted_text: str = ""
    reference_text: str = ""
    conversion_version: str = "manual"
    status: str = "ready"
    error_message: str | None = None
    review_status: str = "pending"
    llm_eval_status: str = "not_started"
    metrics_summary: dict[str, Any] | None = Field(default_factory=dict)
    warnings: str | None = None
    risk_passed: int | None = 1
    risk_blocked: int | None = 0
    fields_snapshot: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ConversionRecordDetailOut(ConversionRecordOut):
    details: list[ConversionDetailOut] = Field(default_factory=list)
    reviews: list[ConversionReviewOut] = Field(default_factory=list)
    reference_annotations: list[dict[str, Any]] = Field(default_factory=list)


class ConversionMetricOut(BaseModel):
    record_id: int
    actual_conversion_count: int
    correct_conversion_count: int
    wrong_conversion_count: int
    missed_conversion_count: int
    over_conversion_count: int
    candidate_count: int
    high_risk_error_count: int
    conversion_accuracy: float
    error_rate: float
    missed_rate: float
    over_conversion_rate: float
    candidate_hit_rate: float
    category_stats: dict[str, Any] = Field(default_factory=dict)


# ========== 批次 ==========

class ConversionBatchCreate(BaseModel):
    name: str
    selected_dates: list[str] = Field(default_factory=list)
    exam_record_ids: list[int] = Field(default_factory=list)
    asr_source_type: str = "latest_success"  # latest_success / config_hash
    asr_config_hash: str | None = None
    conversion_version: str = "manual"


class ConversionBatchOut(BaseModel):
    id: int
    name: str
    date_scope: str = ""
    selected_dates: list[str] = Field(default_factory=list)
    asr_source_type: str = "latest_success"
    asr_config_hash: str | None = None
    conversion_version: str = "manual"
    record_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    reviewed_count: int = 0
    average_accuracy: float = 0.0
    status: str = "draft"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ConversionBatchDetailOut(ConversionBatchOut):
    records: list[ConversionRecordOut] = Field(default_factory=list)


class ConversionBatchCreateResult(BaseModel):
    batch: ConversionBatchOut
    created: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    failed: list[dict[str, Any]] = Field(default_factory=list)
    created_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0

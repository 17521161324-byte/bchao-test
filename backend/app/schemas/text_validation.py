"""Schemas for ASR text validation."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TextValidationRunCreate(BaseModel):
    exam_record_id: int
    asr_result_id: int
    llm_model_id: int | None = None
    prompt_template_id: int | None = None
    correction_template_id: int | None = None
    rule_version_id: int | None = None
    rule_version: str = "manual"
    corrected_text_override: str | None = None


class TextValidationRunOut(BaseModel):
    id: int
    exam_record_id: int
    asr_result_id: int
    llm_model_id: int | None = None
    prompt_template_id: int | None = None
    correction_template_id: int | None = None
    rule_version_id: int | None = None
    record_id_snapshot: str | None = None
    date_snapshot: str | None = None
    asr_model_name: str | None = None
    asr_config_hash: str | None = None
    llm_model_name: str | None = None
    prompt_template_name: str | None = None
    rule_version: str = "manual"
    raw_asr_text: str = ""
    corrected_text: str = ""
    llm_raw_output: str | None = None
    structured_result: dict[str, Any] = Field(default_factory=dict)
    source_spans: list[dict[str, Any]] = Field(default_factory=list)
    conversions: list[dict[str, Any]] = Field(default_factory=list)
    segments: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_items: list[dict[str, Any]] = Field(default_factory=list)
    evaluation: dict[str, Any] = Field(default_factory=dict)
    accuracy: float | None = None
    status: str = "success"
    error_message: str | None = None
    created_at: datetime | None = None

    @field_validator("source_spans", "conversions", "segments", "warnings", "risk_items", mode="before")
    @classmethod
    def normalize_list_fields(cls, value):
        return value or []

    class Config:
        from_attributes = True


class TextCorrectionTemplateCreate(BaseModel):
    name: str
    content: str
    is_default: bool = False


class TextCorrectionTemplateUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    is_default: bool | None = None
    status: str | None = None


class TextCorrectionTemplateOut(BaseModel):
    id: int
    name: str
    content: str
    is_default: bool | int = False
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True

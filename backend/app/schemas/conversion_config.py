"""Schemas for ASR conversion configuration."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConversionVersionCreate(BaseModel):
    version_code: str
    version_name: str
    status: str = "draft"
    description: str = ""


class ConversionVersionUpdate(BaseModel):
    version_code: str | None = None
    version_name: str | None = None
    description: str | None = None
    status: str | None = None


class ConversionVersionClone(BaseModel):
    version_code: str
    version_name: str
    description: str = ""


class ConversionVersionOut(BaseModel):
    id: int
    version_code: str
    version_name: str
    status: str
    description: str = ""
    parent_version_id: int | None = None
    # P0-10：发布回归门槛
    latest_regression_status: str = ""
    latest_regression_config_hash: str = ""
    review_status: str = ""
    created_by: str | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    lexicon_count: int = 0
    rule_count: int = 0

    model_config = {"from_attributes": True}


class ConversionLexiconCreate(BaseModel):
    rule_code: str
    error_text: str
    standard_text: str
    asr_model: str = ""
    business_scene: str = "通用"
    required_context: str = ""
    excluded_context: str = ""
    match_type: str = "exact"
    action: str = "AUTO"
    risk_level: str = "medium"
    confidence: float = 0.95
    priority: int = 100
    enabled: int | bool = 1
    notes: str = ""


class ConversionLexiconUpdate(BaseModel):
    rule_code: str | None = None
    error_text: str | None = None
    standard_text: str | None = None
    asr_model: str | None = None
    business_scene: str | None = None
    required_context: str | None = None
    excluded_context: str | None = None
    match_type: str | None = None
    action: str | None = None
    risk_level: str | None = None
    confidence: float | None = None
    priority: int | None = None
    enabled: int | bool | None = None
    notes: str | None = None


class ConversionLexiconOut(ConversionLexiconCreate):
    id: int
    version_id: int
    hit_count: int = 0
    accuracy: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversionRuleCreate(BaseModel):
    rule_code: str
    rule_type: str
    name: str
    description: str = ""
    pattern: str = ""
    replacement: str = ""
    condition_config: dict[str, Any] = Field(default_factory=dict)
    example_input: str = ""
    example_output: str = ""
    action: str = "AUTO"
    risk_level: str = "medium"
    priority: int = 100
    enabled: int | bool = 1
    editable: int | bool = 0
    system_handler: str = ""
    notes: str = ""


class ConversionRuleUpdate(BaseModel):
    rule_code: str | None = None
    rule_type: str | None = None
    name: str | None = None
    description: str | None = None
    pattern: str | None = None
    replacement: str | None = None
    condition_config: dict[str, Any] | None = None
    example_input: str | None = None
    example_output: str | None = None
    action: str | None = None
    risk_level: str | None = None
    priority: int | None = None
    enabled: int | bool | None = None
    editable: int | bool | None = None
    system_handler: str | None = None
    notes: str | None = None


class ConversionRuleOut(ConversionRuleCreate):
    id: int
    version_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversionPreviewRequest(BaseModel):
    text: str
    version_id: int | None = None
    version_code: str | None = None
    scene: str = ""
    model_name: str = ""
    skip_conversion: bool = False

    model_config = {"protected_namespaces": ()}


class ConversionPreviewOut(BaseModel):
    raw_text: str
    converted_text: str
    conversions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)
    source_spans: list[dict[str, Any]] = Field(default_factory=list)
    segments: list[dict[str, Any]] = Field(default_factory=list)  # 业务片段（医学名词/定位词/数据/噪声）
    risk_items: list[dict[str, Any]] = Field(default_factory=list)  # 警示项（含人工复核建议）
    risk_passed: bool = True
    risk_blocked: bool = False
    version: ConversionVersionOut | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)  # 可观测流水线步骤快照
    result_level: str = "AUTO_ACCEPT"  # AUTO_ACCEPT / REVIEW_REQUIRED / MANUAL_AUDIO_REVIEW
    config_hash: str = ""


class BuiltinRuleItem(BaseModel):
    """内置规则条目（只读展示）。字段与 DB 规则条目兼容，缺失字段可为空。"""
    rule_code: str
    name: str
    description: str = ""
    severity: str = ""
    action: str = ""
    field_code: str = ""
    range: str = ""
    system_handler: str = ""


class BuiltinRulesOut(BaseModel):
    """内置规则清单元数据：CORE词典 / 数字 / 业务片段 / 字段 / 风险。"""
    medical_term: list[BuiltinRuleItem] = Field(default_factory=list)
    number_normalize: list[BuiltinRuleItem] = Field(default_factory=list)
    business_segment: list[BuiltinRuleItem] = Field(default_factory=list)
    text_switch: list[BuiltinRuleItem] = Field(default_factory=list)
    field_extract: list[BuiltinRuleItem] = Field(default_factory=list)
    risk: list[BuiltinRuleItem] = Field(default_factory=list)

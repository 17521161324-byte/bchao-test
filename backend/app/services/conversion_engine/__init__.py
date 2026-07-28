"""ASR 文本转化引擎入口。

处理链路：
    ASR原文 → 基础清洗 → 数字标准化 → 医学术语纠错 → 字段预解析 → 风险拦截

本模块实现完整五步转化流程。
"""
from dataclasses import dataclass, field
from typing import Optional, Any

from app.services.conversion_engine.base_cleaning import apply_base_cleaning
from app.services.conversion_engine.number_normalize import apply_number_normalize
from app.services.conversion_engine.medical_term_correct import apply_medical_term_correct
from app.services.conversion_engine.field_parser import parse_fields
from app.services.conversion_engine.risk_intercept import check_risks, RiskCheckResult


@dataclass
class ConversionResult:
    """单条转化结果"""
    raw_text: str
    normalized_text: str
    conversions: list[dict] = field(default_factory=list)  # 每次转化的记录
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False  # 是否跳过转化（如 skip_conversion=True）

    # 字段解析结果
    fields: dict[str, Any] = field(default_factory=dict)  # 解析出的结构化字段
    source_spans: list[dict] = field(default_factory=list)  # 来源追踪

    # 风险检查结果
    risk_result: Optional[RiskCheckResult] = None
    risk_passed: bool = True  # 风险检查是否通过
    risk_blocked: bool = False  # 是否被阻断


@dataclass
class ConversionDetail:
    """单个转化片段"""
    raw_span: str
    converted_span: str
    raw_start: int
    raw_end: int
    action: str  # AUTO / CANDIDATE / REVIEW / BLOCK
    category: str  # number_format / medical_term / format / etc.
    rule_id: str
    rule_version: str = "V1.0"
    confidence: float = 1.0
    risk_level: str = "low"  # low / medium / high / highest
    risk_type: Optional[str] = None
    notes: Optional[str] = None


def run_conversion(
    raw_text: str,
    scene: str = "",
    model_name: str = "model_c",
    conversion_version: str = "V1.0",
    skip_conversion: bool = False,
) -> ConversionResult:
    """执行完整的文本转化流程。

    Args:
        raw_text: ASR 原始文本
        scene: 业务场景，为空时自动推断
        model_name: ASR 模型名称
        conversion_version: 规则版本
        skip_conversion: 是否跳过转化

    Returns:
        ConversionResult 包含标准化文本、转化记录、字段解析和风险检查结果
    """
    if skip_conversion:
        return ConversionResult(
            raw_text=raw_text,
            normalized_text=raw_text,
            skipped=True,
        )

    result = ConversionResult(raw_text=raw_text, normalized_text=raw_text)

    # 步骤1: 基础清洗
    cleaning_result = apply_base_cleaning(raw_text)
    result.normalized_text = cleaning_result.text
    result.conversions.extend(cleaning_result.conversions)
    result.warnings.extend(cleaning_result.warnings)

    # 步骤2: 数字标准化
    number_result = apply_number_normalize(result.normalized_text, scene=scene)
    result.normalized_text = number_result.text
    result.conversions.extend(number_result.conversions)
    result.warnings.extend(number_result.warnings)

    # 步骤3: 医学术语纠错
    medical_result = apply_medical_term_correct(result.normalized_text, scene=scene)
    result.normalized_text = medical_result.text
    result.conversions.extend(medical_result.conversions)
    result.warnings.extend(medical_result.warnings)

    # 步骤4: 字段解析
    parse_result = parse_fields(result.normalized_text)
    result.fields = parse_result.fields
    result.source_spans = parse_result.source_spans
    result.warnings.extend(parse_result.warnings)

    # 步骤5: 风险拦截
    risk_result = check_risks(
        raw_text=raw_text,
        normalized_text=result.normalized_text,
        conversions=result.conversions,
        fields=result.fields,
        source_spans=result.source_spans,
    )
    result.risk_result = risk_result
    result.risk_passed = risk_result.passed
    result.risk_blocked = risk_result.blocked
    result.warnings.extend(risk_result.warnings)

    return result

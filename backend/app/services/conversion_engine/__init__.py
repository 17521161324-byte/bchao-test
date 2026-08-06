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
from app.services.conversion_engine.business_segment_convert import apply_business_segment_conversion
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

    # 可观测流水线新增字段（兼容：旧调用者不受影响）
    steps: list[Any] = field(default_factory=list)
    result_level: Optional[Any] = None
    config_hash: str = ""


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
    extra_confusion_rules: list[dict] | None = None,
    rule_mode: str = "builtin",
    runtime_rules: list[dict] | None = None,
    config_hash: str = "",
    lexicon_mode: str | None = None,
) -> ConversionResult:
    """执行完整的文本转化流程（兼容入口，内部调用可观测流水线）。

    Args:
        raw_text: ASR 原始文本
        scene: 业务场景，为空时自动推断
        model_name: ASR 模型名称
        conversion_version: 规则版本
        skip_conversion: 是否跳过转化
        extra_confusion_rules: 额外词库规则（数据库词条）
        rule_mode: builtin/replace/append（规则版本语义）
        lexicon_mode: 与 rule_mode 同义（方案命名），优先于 rule_mode
        runtime_rules: 参数化规则列表（数据库 editable=1 规则）
        config_hash: 配置快照哈希

    Returns:
        ConversionResult 保留旧字段（raw_text/normalized_text/conversions/warnings/
        fields/source_spans/risk_result/risk_passed/risk_blocked），
        新增 steps/result_level/config_hash。
    """
    if skip_conversion:
        return ConversionResult(
            raw_text=raw_text,
            normalized_text=raw_text,
            skipped=True,
        )

    from app.services.conversion_pipeline.orchestrator import run_pipeline

    effective_mode = lexicon_mode if lexicon_mode is not None else rule_mode

    pipeline = run_pipeline(
        raw_text=raw_text,
        scene=scene,
        model_name=model_name,
        conversion_version=conversion_version,
        lexicon_rules=extra_confusion_rules or [],
        runtime_rules=runtime_rules or [],
        rule_mode=effective_mode,
        config_hash=config_hash,
    )

    result = ConversionResult(
        raw_text=pipeline.raw_text,
        normalized_text=pipeline.normalized_text,
        conversions=pipeline.conversions,
        warnings=pipeline.warnings,
        fields=pipeline.fields,
        source_spans=pipeline.source_spans,
    )
    result.risk_result = RiskCheckResult(
        passed=pipeline.risk_passed,
        blocked=pipeline.risk_blocked,
        warnings=pipeline.warnings,
        risk_items=pipeline.risk_items,
        actions=[{"rule_id": item.get("rule_id"), "action": item.get("action"), "message": item.get("message")} for item in pipeline.risk_items],
    )
    result.risk_passed = pipeline.risk_passed
    result.risk_blocked = pipeline.risk_blocked
    result.steps = pipeline.steps
    result.result_level = pipeline.result_level
    result.config_hash = pipeline.config_hash

    return result

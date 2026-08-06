"""流水线编排器：固定 7 步可观测执行。

对应改造计划 Task 11：
- BASE_CLEANING → NUMBER_NORMALIZE → MEDICAL_TERM → BUSINESS_SEGMENT →
  FIELD_PARSE → RUNTIME_RULE → RISK_INTERCEPT
- 每步生成 PipelineStepSnapshot（输入/输出/耗时/规则命中/状态前后）
- NUMBER_NORMALIZE 集成尺寸候选解析（D001-D003，REVIEW 候选只记录不改文本）
- resolve_result_level()：BLOCK→MANUAL_AUDIO_REVIEW；REVIEW/CANDIDATE→REVIEW_REQUIRED；
  否则 AUTO_ACCEPT
- run_conversion() 兼容入口保留（旧字段不变，新增 steps/result_level/config_hash）
"""
from __future__ import annotations

import time
from typing import Any

from app.services.conversion_pipeline.context import PipelineContext
from app.services.conversion_pipeline.dimension_parser import parse_dimension_candidates
from app.services.conversion_pipeline.runtime_rule_executor import execute_runtime_rules
from app.services.conversion_pipeline.types import (
    ResultLevel,
    StepCode,
    STEP_NAMES,
    STEP_ORDER,
    PipelineRunResult,
    PipelineStepSnapshot,
)
from app.services.conversion_engine.base_cleaning import apply_base_cleaning
from app.services.conversion_engine.business_segment_convert import apply_business_segment_conversion
from app.services.conversion_engine.field_parser import parse_fields
from app.services.conversion_engine.medical_term_correct import apply_medical_term_correct
from app.services.conversion_engine.number_normalize import apply_number_normalize
from app.services.conversion_engine.risk_intercept import check_risks


def _snapshot(
    step_code: StepCode,
    status: str,
    input_text: str,
    output_text: str,
    *,
    conversions: list[dict[str, Any]] | None = None,
    rule_hits: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    state_before: dict[str, Any] | None = None,
    state_after: dict[str, Any] | None = None,
    fields: dict[str, Any] | None = None,
    source_spans: list[dict[str, Any]] | None = None,
    duration_ms: int = 0,
    error_message: str | None = None,
) -> PipelineStepSnapshot:
    return PipelineStepSnapshot(
        step_code=step_code.value,
        step_name=STEP_NAMES[step_code],
        step_order=STEP_ORDER[step_code],
        status=status,
        input_text=input_text,
        output_text=output_text,
        conversions=conversions or [],
        rule_hits=rule_hits or [],
        warnings=warnings or [],
        state_before=state_before or {},
        state_after=state_after or {},
        fields=fields or {},
        source_spans=source_spans or [],
        duration_ms=duration_ms,
        error_message=error_message,
    )


def resolve_result_level(
    risk_items: list[dict[str, Any]],
    conversions: list[dict[str, Any]],
) -> ResultLevel:
    """结果分级：出现 BLOCK→MANUAL_AUDIO_REVIEW；有 REVIEW/CANDIDATE→REVIEW_REQUIRED；否则 AUTO_ACCEPT。"""
    actions = [item.get("action") for item in risk_items] + [c.get("action") for c in conversions]
    if any(a == "BLOCK" for a in actions):
        return ResultLevel.MANUAL_AUDIO_REVIEW
    if any(a in ("REVIEW", "CANDIDATE") for a in actions):
        return ResultLevel.REVIEW_REQUIRED
    return ResultLevel.AUTO_ACCEPT


def run_pipeline(
    *,
    raw_text: str,
    scene: str = "",
    model_name: str = "model_c",
    conversion_version: str = "V1.0",
    lexicon_rules: list[dict[str, Any]] | None = None,
    runtime_rules: list[dict[str, Any]] | None = None,
    rule_mode: str = "builtin",
    config_hash: str = "",
) -> PipelineRunResult:
    """执行固定 7 步流水线并返回快照与结果。"""
    ctx = PipelineContext(
        raw_text=raw_text,
        current_text=raw_text,
        scene=scene,
        model_name=model_name,
        conversion_version=conversion_version,
        config_hash=config_hash,
        lexicon_rules=lexicon_rules or [],
        runtime_rules=runtime_rules or [],
    )

    steps: list[PipelineStepSnapshot] = []

    # 第 1 步：基础清洗
    started = time.monotonic()
    try:
        cleaning = apply_base_cleaning(ctx.current_text)
        ctx.current_text = cleaning.text
        ctx.conversions.extend(cleaning.conversions)
        ctx.warnings.extend(cleaning.warnings)
        steps.append(_snapshot(
            StepCode.BASE_CLEANING, "success", ctx.raw_text, ctx.current_text,
            conversions=cleaning.conversions, warnings=cleaning.warnings,
            state_before=ctx.parser_state.to_dict(), state_after=ctx.parser_state.to_dict(),
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        steps.append(_snapshot(
            StepCode.BASE_CLEANING, "failed", ctx.current_text, ctx.current_text,
            error_message=str(exc), duration_ms=int((time.monotonic() - started) * 1000),
        ))

    # 第 2 步：数字与尺寸解析
    started = time.monotonic()
    try:
        number = apply_number_normalize(ctx.current_text, scene=scene)
        ctx.current_text = number.text
        ctx.conversions.extend(number.conversions)
        ctx.warnings.extend(number.warnings)
        # 尺寸候选解析（D001-D003）：REVIEW 候选只记录为 rule_hits，不静默改文本
        candidates = parse_dimension_candidates(ctx.current_text)
        candidate_hits = [
            {
                "rule_id": c.rule_id,
                "raw": c.raw,
                "normalized": c.normalized,
                "action": c.action,
                "warning_code": c.warning_code,
                "message": c.message,
            }
            for c in candidates
        ]
        steps.append(_snapshot(
            StepCode.NUMBER_NORMALIZE, "success", steps[-1].output_text if steps else ctx.raw_text,
            ctx.current_text,
            conversions=number.conversions, rule_hits=candidate_hits, warnings=number.warnings,
            state_before=ctx.parser_state.to_dict(), state_after=ctx.parser_state.to_dict(),
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        steps.append(_snapshot(
            StepCode.NUMBER_NORMALIZE, "failed", ctx.current_text, ctx.current_text,
            error_message=str(exc), duration_ms=int((time.monotonic() - started) * 1000),
        ))

    # 第 3 步：医学词处理
    started = time.monotonic()
    try:
        medical = apply_medical_term_correct(
            ctx.current_text,
            scene=scene,
            extra_rules=ctx.lexicon_rules,
            rule_mode=rule_mode,
            decision_registry=ctx.decision_registry,
            rule_version=conversion_version,
        )
        ctx.current_text = medical.text
        ctx.conversions.extend(medical.conversions)
        ctx.warnings.extend(medical.warnings)
        steps.append(_snapshot(
            StepCode.MEDICAL_TERM, "success", steps[-1].output_text if steps else ctx.raw_text,
            ctx.current_text,
            conversions=medical.conversions, warnings=medical.warnings,
            state_before=ctx.parser_state.to_dict(), state_after=ctx.parser_state.to_dict(),
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        steps.append(_snapshot(
            StepCode.MEDICAL_TERM, "failed", ctx.current_text, ctx.current_text,
            error_message=str(exc), duration_ms=int((time.monotonic() - started) * 1000),
        ))

    # 第 4 步：业务片段定位与安全转换
    started = time.monotonic()
    try:
        business_text, business_conversions = apply_business_segment_conversion(
            ctx.current_text,
            decision_registry=ctx.decision_registry,
            rule_version=conversion_version,
        )
        ctx.current_text = business_text
        ctx.conversions.extend(business_conversions)
        steps.append(_snapshot(
            StepCode.BUSINESS_SEGMENT, "success", steps[-1].output_text if steps else ctx.raw_text,
            ctx.current_text,
            conversions=business_conversions,
            state_before=ctx.parser_state.to_dict(), state_after=ctx.parser_state.to_dict(),
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        steps.append(_snapshot(
            StepCode.BUSINESS_SEGMENT, "failed", ctx.current_text, ctx.current_text,
            error_message=str(exc), duration_ms=int((time.monotonic() - started) * 1000),
        ))

    # 第 5 步：上下文状态机与字段解析
    started = time.monotonic()
    try:
        state_before = ctx.parser_state.to_dict()
        parse_result = parse_fields(ctx.current_text)
        ctx.fields = parse_result.fields
        ctx.source_spans = parse_result.source_spans
        ctx.warnings.extend(parse_result.warnings)
        steps.append(_snapshot(
            StepCode.FIELD_PARSE, "success", steps[-1].output_text if steps else ctx.raw_text,
            ctx.current_text,
            warnings=parse_result.warnings, state_before=state_before,
            state_after=ctx.parser_state.to_dict(),
            fields=parse_result.fields, source_spans=parse_result.source_spans,
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        steps.append(_snapshot(
            StepCode.FIELD_PARSE, "failed", ctx.current_text, ctx.current_text,
            error_message=str(exc), duration_ms=int((time.monotonic() - started) * 1000),
        ))

    # 第 6 步：参数化规则执行
    started = time.monotonic()
    try:
        runtime_result = execute_runtime_rules(ctx, ctx.runtime_rules)
        ctx.current_text = runtime_result.text
        ctx.fields = runtime_result.fields
        ctx.warnings.extend(runtime_result.warnings)
        steps.append(_snapshot(
            StepCode.RUNTIME_RULE, "success", steps[-1].output_text if steps else ctx.raw_text,
            ctx.current_text,
            conversions=runtime_result.applied, warnings=runtime_result.warnings,
            state_before=ctx.parser_state.to_dict(), state_after=ctx.parser_state.to_dict(),
            fields=runtime_result.fields,
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        steps.append(_snapshot(
            StepCode.RUNTIME_RULE, "failed", ctx.current_text, ctx.current_text,
            error_message=str(exc), duration_ms=int((time.monotonic() - started) * 1000),
        ))

    # 第 7 步：风险校验与分流
    started = time.monotonic()
    try:
        risk_result = check_risks(
            raw_text=ctx.raw_text,
            normalized_text=ctx.current_text,
            conversions=ctx.conversions,
            fields=ctx.fields,
            source_spans=ctx.source_spans,
        )
        ctx.risk_items = risk_result.risk_items
        ctx.warnings.extend(risk_result.warnings)
        steps.append(_snapshot(
            StepCode.RISK_INTERCEPT, "success", steps[-1].output_text if steps else ctx.raw_text,
            ctx.current_text,
            conversions=[item for item in risk_result.risk_items],
            rule_hits=risk_result.risk_items, warnings=risk_result.warnings,
            state_before=ctx.parser_state.to_dict(), state_after=ctx.parser_state.to_dict(),
            fields=ctx.fields,
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        steps.append(_snapshot(
            StepCode.RISK_INTERCEPT, "failed", ctx.current_text, ctx.current_text,
            error_message=str(exc), duration_ms=int((time.monotonic() - started) * 1000),
        ))

    result_level = resolve_result_level(ctx.risk_items, ctx.conversions)
    blocked = any(item.get("action") == "BLOCK" for item in ctx.risk_items)

    return PipelineRunResult(
        raw_text=ctx.raw_text,
        normalized_text=ctx.current_text,
        fields=ctx.fields,
        source_spans=ctx.source_spans,
        conversions=ctx.conversions,
        warnings=ctx.warnings,
        risk_items=ctx.risk_items,
        steps=steps,
        result_level=result_level,
        risk_passed=len(ctx.risk_items) == 0,
        risk_blocked=blocked,
        config_hash=config_hash,
    )


def build_config_hash(snapshot: dict) -> str:
    """配置快照哈希（Task 12）：每次执行冻结规则配置，同一执行内各步骤哈希一致。"""
    import hashlib
    import json

    payload = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

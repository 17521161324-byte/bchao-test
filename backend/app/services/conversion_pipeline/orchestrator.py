"""流水线编排器：固定 7 步可观测执行。

对应改造计划 Task 11：
- BASE_CLEANING → NUMBER_NORMALIZE → MEDICAL_TERM → BUSINESS_SEGMENT →
  FIELD_PARSE → RUNTIME_RULE → RISK_INTERCEPT
- 每步生成 PipelineStepSnapshot（输入/输出/耗时/规则命中/状态前后）
- NUMBER_NORMALIZE 集成尺寸候选解析（D001-D003）：
  先读步骤输入原文解析候选 → apply_dimension_candidates 统一应用
  （AUTO=注册决策+改文本+conversions；REVIEW/CANDIDATE=不改文本+conversions+
  warnings+影响 result_level；??×N 候选提升 BLOCK 并以显式标记写入文本）→
  之后才 apply_number_normalize
- 步骤失败即停：PipelineStepError 抛出后终止后续步骤，结果 status=failed
- resolve_result_level()：BLOCK→MANUAL_AUDIO_REVIEW；REVIEW/CANDIDATE→REVIEW_REQUIRED；
  否则 AUTO_ACCEPT
- run_conversion() 兼容入口保留（旧字段不变，新增 steps/result_level/config_hash）
"""
from __future__ import annotations

import time
from typing import Any, Callable

from app.services.conversion_pipeline.context import PipelineContext
from app.services.conversion_pipeline.dimension_parser import (
    apply_dimension_candidates,
    parse_dimension_candidates,
)
from app.services.conversion_pipeline.runtime_rule_executor import execute_runtime_rules
from app.services.conversion_pipeline.types import (
    ParserState,
    ResultLevel,
    StepCode,
    STEP_NAMES,
    STEP_ORDER,
    PipelineRunResult,
    PipelineStepSnapshot,
)
from app.services.conversion_engine.base_cleaning import apply_base_cleaning
from app.services.conversion_engine.business_segment_convert import apply_business_segment_conversion
from app.services.conversion_engine.business_segment_locator import locate_business_segments
from app.services.conversion_engine.field_parser import parse_fields
from app.services.conversion_engine.medical_term_correct import apply_medical_term_correct
from app.services.conversion_engine.number_normalize import apply_number_normalize
from app.services.conversion_engine.risk_intercept import check_risks


class PipelineStepError(RuntimeError):
    """流水线步骤失败标记：抛出后编排器立即停止后续步骤（P0-04）。"""


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
    state_transitions: list[dict[str, Any]] | None = None,
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
        state_transitions=state_transitions or [],
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


def _record_replacement(
    ctx: PipelineContext,
    start: int,
    end: int,
    replacement: str,
    rule_id: str,
    step_input: str,
) -> None:
    """记录一次文本替换到 SpanMap（P0-07）：把当前坐标映射回原始坐标并记录。"""
    raw_start, raw_end = ctx.span_map.current_to_raw(start, end)
    ctx.span_map.record(
        raw_start=raw_start,
        raw_end=raw_end,
        current_start=start,
        current_end=end,
        raw_text=step_input[start:end],
        current_text=replacement,
        rule_id=rule_id,
    )


def _record_step_replacements(
    ctx: PipelineContext,
    conversions: list[dict[str, Any]],
    step_input: str,
) -> None:
    """把本步骤产生的 AUTO 文本替换批量记录进 SpanMap。"""
    for conv in conversions:
        if conv.get("action") != "AUTO":
            continue
        if "start" not in conv or "end" not in conv:
            continue
        converted = conv.get("converted")
        if converted is None:
            continue
        try:
            _record_replacement(
                ctx,
                int(conv["start"]),
                int(conv["end"]),
                str(converted),
                str(conv.get("rule_id") or conv.get("rule_code") or ""),
                step_input,
            )
        except (TypeError, ValueError):
            continue


# ========== 单步执行函数 ==========

def _step_base_cleaning(ctx: PipelineContext) -> dict[str, Any]:
    cleaning = apply_base_cleaning(ctx.current_text)
    ctx.current_text = cleaning.text
    ctx.conversions.extend(cleaning.conversions)
    ctx.warnings.extend(cleaning.warnings)
    return {"conversions": cleaning.conversions, "warnings": cleaning.warnings}


def _step_number_normalize(ctx: PipelineContext, scene: str) -> dict[str, Any]:
    """数字与尺寸解析：先应用尺寸候选（读步骤输入原文），再普通数字标准化。"""
    step_input = ctx.current_text
    candidates = parse_dimension_candidates(step_input)
    dimension_text, dimension_conversions, dimension_warnings = apply_dimension_candidates(
        step_input,
        candidates,
        registry=ctx.decision_registry,
        rule_version=ctx.conversion_version,
        span_map=ctx.span_map,
    )
    ctx.current_text = dimension_text
    ctx.conversions.extend(dimension_conversions)
    ctx.warnings.extend(dimension_warnings)

    number = apply_number_normalize(ctx.current_text, scene=scene)
    ctx.current_text = number.text
    ctx.conversions.extend(number.conversions)
    ctx.warnings.extend(number.warnings)

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
    return {
        "conversions": dimension_conversions + number.conversions,
        "rule_hits": candidate_hits,
        "warnings": dimension_warnings + number.warnings,
    }


def _step_medical_term(ctx: PipelineContext, scene: str, rule_mode: str) -> dict[str, Any]:
    step_input = ctx.current_text
    medical = apply_medical_term_correct(
        ctx.current_text,
        scene=scene,
        extra_rules=ctx.lexicon_rules,
        rule_mode=rule_mode,
        decision_registry=ctx.decision_registry,
        rule_version=ctx.conversion_version,
    )
    ctx.current_text = medical.text
    ctx.conversions.extend(medical.conversions)
    ctx.warnings.extend(medical.warnings)
    _record_step_replacements(ctx, medical.conversions, step_input)
    return {"conversions": medical.conversions, "warnings": medical.warnings}


def _step_business_segment(ctx: PipelineContext) -> dict[str, Any]:
    step_input = ctx.current_text
    business_text, business_conversions = apply_business_segment_conversion(
        ctx.current_text,
        decision_registry=ctx.decision_registry,
        rule_version=ctx.conversion_version,
    )
    ctx.current_text = business_text
    ctx.conversions.extend(business_conversions)
    _record_step_replacements(ctx, business_conversions, step_input)
    return {
        "conversions": business_conversions,
        "rule_hits": locate_business_segments(ctx.current_text),
    }


def _step_field_parse(ctx: PipelineContext) -> dict[str, Any]:
    parse_result = parse_fields(ctx.current_text)
    ctx.fields = parse_result.fields
    ctx.source_spans = parse_result.source_spans
    ctx.warnings.extend(parse_result.warnings)
    field_rule_items = list(getattr(parse_result, "rule_items", []) or [])
    # M006/M007 are REVIEW decisions. Adding them to global conversions makes
    # resolve_result_level() route the whole execution to REVIEW_REQUIRED.
    ctx.conversions.extend(field_rule_items)
    ctx.parser_state = ParserState.from_dict(parse_result.final_state)
    # P0-07：source_spans 补充 raw_start/raw_end（映射回原始文本坐标）
    for span in ctx.source_spans:
        raw_start, raw_end = ctx.span_map.current_to_raw(
            int(span.get("start") or 0),
            int(span.get("end") or 0),
        )
        span["raw_start"] = raw_start
        span["raw_end"] = raw_end
    return {
        "fields": parse_result.fields,
        "conversions": field_rule_items,
        # 字段解析校验复用业务片段模型，前端可按内膜/右卵巢/左卵巢/备注卡片展示。
        "rule_hits": locate_business_segments(ctx.current_text),
        "source_spans": parse_result.source_spans,
        "warnings": parse_result.warnings,
        "state_after": parse_result.final_state,
        "state_transitions": parse_result.transitions,
    }


def _step_runtime_rule(ctx: PipelineContext) -> dict[str, Any]:
    step_input = ctx.current_text
    runtime_result = execute_runtime_rules(ctx, ctx.runtime_rules)
    ctx.current_text = runtime_result.text
    ctx.fields = runtime_result.fields
    ctx.warnings.extend(runtime_result.warnings)
    # P0-02：参数规则动作进入全局 conversions 与风险分级
    ctx.conversions.extend(runtime_result.applied)
    ctx.risk_items.extend(runtime_result.risk_items)
    _record_step_replacements(ctx, runtime_result.applied, step_input)
    return {
        "conversions": runtime_result.applied,
        "warnings": runtime_result.warnings,
        "fields": runtime_result.fields,
    }


def _step_risk_intercept(ctx: PipelineContext) -> dict[str, Any]:
    risk_result = check_risks(
        raw_text=ctx.raw_text,
        normalized_text=ctx.current_text,
        conversions=ctx.conversions,
        fields=ctx.fields,
        source_spans=ctx.source_spans,
    )
    ctx.risk_items = risk_result.risk_items
    ctx.warnings.extend(risk_result.warnings)
    return {
        "conversions": list(risk_result.risk_items),
        "rule_hits": risk_result.risk_items,
        "warnings": risk_result.warnings,
    }


def _build_step_functions(scene: str, rule_mode: str) -> list[tuple[StepCode, Callable[[PipelineContext], dict[str, Any]]]]:
    """绑定步骤函数所需的场景/规则模式参数。"""
    from functools import partial

    return [
        # 医学词必须先于中文数字处理，避免“五回声”等医学近音词被数字规则拆坏。
        (StepCode.MEDICAL_TERM, partial(_step_medical_term, scene=scene, rule_mode=rule_mode)),
        (StepCode.BASE_CLEANING, _step_base_cleaning),
        (StepCode.NUMBER_NORMALIZE, partial(_step_number_normalize, scene=scene)),
        (StepCode.BUSINESS_SEGMENT, _step_business_segment),
        (StepCode.FIELD_PARSE, _step_field_parse),
        (StepCode.RUNTIME_RULE, _step_runtime_rule),
        (StepCode.RISK_INTERCEPT, _step_risk_intercept),
    ]


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
    start_step: StepCode | str | None = None,
    stop_after_step: StepCode | str | None = None,
    initial_text: str | None = None,
) -> PipelineRunResult:
    """执行固定 7 步流水线并返回快照与结果。

    Args:
        start_step: 从指定步骤开始执行（之前的步骤不执行、不生成快照）。
        stop_after_step: 执行到该步骤后停止（用于单步/执行到指定步骤）。
        initial_text: 起始文本（继续执行时用上一已保存步骤的有效输出）。
    """
    if start_step is not None and not isinstance(start_step, StepCode):
        start_step = StepCode(start_step)
    if stop_after_step is not None and not isinstance(stop_after_step, StepCode):
        stop_after_step = StepCode(stop_after_step)

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
    if initial_text is not None:
        ctx.current_text = initial_text

    steps: list[PipelineStepSnapshot] = []
    ctx.steps = steps

    failed = False
    try:
        step_functions = _build_step_functions(scene=scene, rule_mode=rule_mode)
        for step_code, step_fn in step_functions:
            if start_step is not None and STEP_ORDER[step_code] < STEP_ORDER[start_step]:
                continue
            step_input = ctx.current_text
            state_before = ctx.parser_state.to_dict()
            started = time.monotonic()
            try:
                extras = step_fn(ctx)
            except Exception as exc:  # noqa: BLE001
                ctx.steps.append(_snapshot(
                    step_code, "failed", step_input, ctx.current_text,
                    error_message=str(exc),
                    state_before=state_before,
                    state_after=ctx.parser_state.to_dict(),
                    duration_ms=int((time.monotonic() - started) * 1000),
                ))
                raise PipelineStepError(str(exc)) from exc
            duration_ms = int((time.monotonic() - started) * 1000)
            state_after = extras.get("state_after") or ctx.parser_state.to_dict()
            ctx.steps.append(_snapshot(
                step_code, "success", step_input, ctx.current_text,
                conversions=extras.get("conversions"),
                rule_hits=extras.get("rule_hits"),
                warnings=extras.get("warnings"),
                state_before=state_before,
                state_after=state_after,
                state_transitions=extras.get("state_transitions"),
                fields=extras.get("fields"),
                source_spans=extras.get("source_spans"),
                duration_ms=duration_ms,
            ))
            if stop_after_step is not None and step_code == stop_after_step:
                break
    except PipelineStepError:
        failed = True

    result_level = resolve_result_level(ctx.risk_items, ctx.conversions)
    blocked = (
        any(item.get("action") == "BLOCK" for item in ctx.risk_items)
        or any(item.get("action") == "BLOCK" for item in ctx.conversions)
    )

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
        status="failed" if failed else "completed",
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

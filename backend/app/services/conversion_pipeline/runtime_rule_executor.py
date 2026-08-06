"""参数化规则执行器：让数据库参数规则真正执行（安全白名单机制）。

对应改造计划 Task 10：
- 只允许白名单 handler：regex_replace / field_threshold / field_format / field_reclassify
- 不支持的 system_handler 跳过并生成配置错误警示
- 不得 eval / exec / 动态 import / getattr 任意模块
- 转换前必须经过 DecisionRegistry
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.conversion_pipeline.context import PipelineContext
from app.services.conversion_pipeline.decision_registry import DecisionRegistry
from app.services.conversion_pipeline.types import RuleDecision, StepCode


ALLOWED_HANDLERS = {
    "regex_replace",
    "field_threshold",
    "field_format",
    "field_reclassify",
}

SUPPORTED_OPERATORS = {"lt", "lte", "gt", "gte", "eq"}


@dataclass
class RuntimeRuleResult:
    text: str
    applied: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)


def _matches_context(condition: dict[str, Any], text: str) -> bool:
    required = condition.get("required_terms") or []
    excluded = condition.get("excluded_terms") or []
    if excluded and any(term in text for term in excluded):
        return False
    if required and not any(term in text for term in required):
        return False
    return True


def _apply_regex_replace(
    text: str,
    rule: dict[str, Any],
    *,
    decision_registry: DecisionRegistry | None,
    rule_version: str,
    result: RuntimeRuleResult,
) -> str:
    pattern = rule.get("pattern") or ""
    replacement = rule.get("replacement") or ""
    if not pattern:
        result.warnings.append(f"规则 {rule.get('rule_code', '')} 缺少 pattern")
        return text
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        result.warnings.append(f"规则 {rule.get('rule_code', '')} 正则无效: {exc}")
        return text

    if not _matches_context(rule.get("condition_config") or {}, text):
        return text

    def _do_replace(match: re.Match) -> str:
        start, end = match.start(), match.end()
        if decision_registry is not None:
            decision = RuleDecision(
                rule_id=rule.get("rule_code") or "",
                rule_version=rule_version,
                step_code=StepCode.RUNTIME_RULE.value,
                action=str(rule.get("action") or "AUTO"),
                category="runtime_rule",
                raw=match.group(0),
                converted=replacement,
                start=start,
                end=end,
                risk_level=str(rule.get("risk_level") or "medium"),
            )
            if not decision_registry.register(decision):
                return match.group(0)
        result.applied.append({
            "rule_code": rule.get("rule_code") or "",
            "handler": "regex_replace",
            "raw": match.group(0),
            "converted": replacement,
            "start": start,
            "end": end,
            "action": rule.get("action") or "AUTO",
            "risk_level": rule.get("risk_level") or "medium",
        })
        return replacement

    return compiled.sub(_do_replace, text)


def _parse_numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _apply_field_threshold(
    rule: dict[str, Any],
    fields: dict[str, Any],
    result: RuntimeRuleResult,
) -> None:
    condition = rule.get("condition_config") or {}
    field_codes = condition.get("field_codes") or []
    operator = condition.get("operator") or "lt"
    threshold = condition.get("threshold")
    warning_code = condition.get("warning_code") or ""
    if operator not in SUPPORTED_OPERATORS or threshold is None:
        result.warnings.append(f"规则 {rule.get('rule_code', '')} 阈值配置不支持")
        return
    for field_code in field_codes:
        value = fields.get(field_code)
        if value is None:
            continue
        num = _parse_numeric(value)
        if num is None:
            continue
        matched = {
            "lt": num < threshold,
            "lte": num <= threshold,
            "gt": num > threshold,
            "gte": num >= threshold,
            "eq": num == threshold,
        }[operator]
        if matched:
            message = f"{field_code}={value} 触发阈值规则 {rule.get('rule_code', '')}（{operator} {threshold}）"
            result.warnings.append(message)
            result.applied.append({
                "rule_code": rule.get("rule_code") or "",
                "handler": "field_threshold",
                "field_code": field_code,
                "value": value,
                "warning_code": warning_code,
                "action": rule.get("action") or "REVIEW",
            })


def _apply_field_format(
    rule: dict[str, Any],
    fields: dict[str, Any],
    result: RuntimeRuleResult,
) -> None:
    condition = rule.get("condition_config") or {}
    field_codes = condition.get("field_codes") or []
    pattern = condition.get("pattern") or ""
    warning_code = condition.get("warning_code") or ""
    if not pattern:
        return
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        result.warnings.append(f"规则 {rule.get('rule_code', '')} 格式正则无效: {exc}")
        return
    for field_code in field_codes:
        value = fields.get(field_code)
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            text = str(item)
            if not compiled.fullmatch(text):
                result.warnings.append(f"{field_code} 值 {text} 不符合格式 {pattern}（{warning_code}）")
                result.applied.append({
                    "rule_code": rule.get("rule_code") or "",
                    "handler": "field_format",
                    "field_code": field_code,
                    "value": text,
                    "warning_code": warning_code,
                    "action": rule.get("action") or "REVIEW",
                })


def _apply_field_reclassify(
    rule: dict[str, Any],
    fields: dict[str, Any],
    result: RuntimeRuleResult,
) -> None:
    condition = rule.get("condition_config") or {}
    source_field = condition.get("source_field") or ""
    target_field = condition.get("target_field") or ""
    required_suffixes = condition.get("required_suffixes") or []
    if not source_field or not target_field:
        return
    source = fields.get(source_field)
    if not isinstance(source, list) or not source:
        return
    moved: list[Any] = []
    kept: list[Any] = []
    for item in source:
        raw = str(item.get("raw_text", item) if isinstance(item, dict) else item)
        if any(raw.endswith(suffix) for suffix in required_suffixes):
            moved.append(item)
        else:
            kept.append(item)
    if moved:
        fields[source_field] = kept
        target = fields.get(target_field)
        if not isinstance(target, list):
            target = []
        for item in moved:
            value = item.get("value", item) if isinstance(item, dict) else item
            if isinstance(value, dict):
                target.append(value)
            else:
                target.append({"type": str(value), "negated": False})
        fields[target_field] = target
        result.applied.append({
            "rule_code": rule.get("rule_code") or "",
            "handler": "field_reclassify",
            "source_field": source_field,
            "target_field": target_field,
            "moved": len(moved),
            "action": rule.get("action") or "AUTO",
        })


def run_rule(
    text: str,
    rule: dict[str, Any],
    *,
    fields: dict[str, Any] | None = None,
    decision_registry: DecisionRegistry | None = None,
    rule_version: str = "V1.0",
) -> RuntimeRuleResult:
    """单条参数化规则执行（测试与编排均使用）。"""
    result = RuntimeRuleResult(text=text, fields=dict(fields or {}))

    if not rule.get("enabled", True):
        return result

    handler = rule.get("system_handler") or ""
    if handler not in ALLOWED_HANDLERS:
        result.warnings.append(
            f"规则 {rule.get('rule_code', '')} 使用了不支持的处理器 {handler}，已跳过"
        )
        return result

    if handler == "regex_replace":
        result.text = _apply_regex_replace(
            text, rule, decision_registry=decision_registry, rule_version=rule_version, result=result
        )
    elif handler == "field_threshold":
        _apply_field_threshold(rule, result.fields, result)
    elif handler == "field_format":
        _apply_field_format(rule, result.fields, result)
    elif handler == "field_reclassify":
        _apply_field_reclassify(rule, result.fields, result)

    return result


def execute_runtime_rules(
    context: PipelineContext,
    rules: list[dict[str, Any]],
) -> RuntimeRuleResult:
    """按顺序执行参数化规则（编排器第 6 步调用）。"""
    result = RuntimeRuleResult(text=context.current_text, fields=dict(context.fields))
    for rule in rules:
        step = run_rule(
            result.text,
            rule,
            fields=result.fields,
            decision_registry=context.decision_registry,
            rule_version=context.conversion_version,
        )
        result.text = step.text
        result.fields = step.fields
        result.applied.extend(step.applied)
        result.warnings.extend(step.warnings)
    return result

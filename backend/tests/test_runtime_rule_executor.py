"""参数化规则执行器测试（Task 10）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.conversion_pipeline.context import PipelineContext
from app.services.conversion_pipeline.runtime_rule_executor import (
    execute_runtime_rules,
    run_rule,
)


def _context(text: str = "卵巢看完了放边看卵泡") -> PipelineContext:
    return PipelineContext(
        raw_text=text,
        current_text=text,
        scene="卵泡监测B超",
        model_name="model_c",
        conversion_version="V1.0",
        config_hash="test-hash",
    )


def test_unknown_system_handler_is_not_executed():
    rule = {
        "rule_code": "BAD",
        "system_handler": "__import__",
        "enabled": True,
    }
    result = execute_runtime_rules(_context(), [rule])
    assert result.applied == []
    assert any("不支持" in item for item in result.warnings)


def test_regex_replace_respects_required_context():
    rule = {
        "rule_code": "P001",
        "system_handler": "regex_replace",
        "pattern": "放边",
        "replacement": "换边",
        "condition_config": {
            "required_terms": ["卵泡", "卵巢"],
            "excluded_terms": [],
        },
        "action": "AUTO",
        "risk_level": "medium",
        "priority": 100,
        "enabled": True,
    }

    no_context = run_rule("请把东西放边上", rule)
    assert no_context.text == "请把东西放边上"

    with_context = run_rule("卵巢看完了放边看卵泡", rule)
    assert "换边" in with_context.text


def test_runtime_review_regex_does_not_mutate_text():
    """P0-03：REVIEW 正则规则命中后不修改医疗文本。"""
    result = run_rule(
        "五回声",
        {
            "rule_code": "P001",
            "system_handler": "regex_replace",
            "pattern": "五回声",
            "replacement": "无回声",
            "action": "REVIEW",
            "enabled": True,
        },
    )
    assert result.text == "五回声"
    assert result.applied[0]["action"] == "REVIEW"
    assert any("不修改原文" in item for item in result.warnings)


def test_runtime_block_regex_does_not_mutate_text():
    """P0-03：BLOCK 正则规则命中后不修改医疗文本，并生成 BLOCK risk_item。"""
    result = run_rule(
        "五回声",
        {
            "rule_code": "P002",
            "system_handler": "regex_replace",
            "pattern": "五回声",
            "replacement": "无回声",
            "action": "BLOCK",
            "risk_level": "highest",
            "enabled": True,
        },
    )
    assert result.text == "五回声"
    assert result.applied[0]["action"] == "BLOCK"
    assert any(item["action"] == "BLOCK" for item in result.risk_items)


def test_invalid_regex_only_warns():
    rule = {
        "rule_code": "P_BAD_REGEX",
        "system_handler": "regex_replace",
        "pattern": "([unclosed",
        "replacement": "x",
        "condition_config": {},
        "enabled": True,
    }
    result = run_rule("测试文本", rule)
    assert result.text == "测试文本"
    assert any("正则无效" in item for item in result.warnings)


def test_field_threshold_warns_on_small_ovary():
    rule = {
        "rule_code": "P_OVARY_MIN_10",
        "system_handler": "field_threshold",
        "condition_config": {
            "field_codes": ["right_ovary_size", "left_ovary_size"],
            "value_mode": "any_dimension",
            "operator": "lt",
            "threshold": 10,
            "warning_code": "OVARY_SIZE_BELOW_10",
        },
        "action": "REVIEW",
        "risk_level": "high",
        "enabled": True,
    }
    result = run_rule(
        "左卵巢大小8×32",
        rule,
        fields={"left_ovary_size": "8×32"},
    )
    assert any(item["warning_code"] == "OVARY_SIZE_BELOW_10" for item in result.applied)


def test_field_format_flags_invalid_follicle():
    rule = {
        "rule_code": "P_FOLLICLE_FORMAT",
        "system_handler": "field_format",
        "condition_config": {
            "field_codes": ["right_follicles"],
            "pattern": r"^\d{1,2}\.\d$",
            "warning_code": "FOLLICLE_FORMAT_INVALID",
        },
        "action": "REVIEW",
        "risk_level": "high",
        "enabled": True,
    }
    result = run_rule(
        "",
        rule,
        fields={"right_follicles": ["13", "13.8"]},
    )
    assert any(
        item["warning_code"] == "FOLLICLE_FORMAT_INVALID" and item["value"] == "13"
        for item in result.applied
    )
    assert not any(item["value"] == "13.8" for item in result.applied)

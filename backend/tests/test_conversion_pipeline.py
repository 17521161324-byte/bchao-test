"""流水线核心类型与决策注册表测试（Task 1-2）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.conversion_pipeline.decision_registry import DecisionRegistry
from app.services.conversion_pipeline.types import (
    ACTION_PRECEDENCE,
    RuleDecision,
    StepCode,
    STEP_ORDER,
)
from app.services.conversion_engine.business_segment_convert import apply_business_segment_conversion


def test_step_order_is_stable():
    assert STEP_ORDER[StepCode.BASE_CLEANING] == 10
    assert STEP_ORDER[StepCode.NUMBER_NORMALIZE] == 20
    assert STEP_ORDER[StepCode.MEDICAL_TERM] == 30
    assert STEP_ORDER[StepCode.BUSINESS_SEGMENT] == 40
    assert STEP_ORDER[StepCode.FIELD_PARSE] == 50
    assert STEP_ORDER[StepCode.RUNTIME_RULE] == 60
    assert STEP_ORDER[StepCode.RISK_INTERCEPT] == 70


def test_action_precedence_blocks_auto_downgrade():
    assert ACTION_PRECEDENCE["BLOCK"] > ACTION_PRECEDENCE["REVIEW"]
    assert ACTION_PRECEDENCE["REVIEW"] > ACTION_PRECEDENCE["AUTO"]
    assert ACTION_PRECEDENCE["AUTO"] > ACTION_PRECEDENCE["NONE"]


def test_review_decision_blocks_later_auto_on_same_span():
    registry = DecisionRegistry()
    review = RuleDecision(
        rule_id="C005",
        rule_version="V1",
        step_code="MEDICAL_TERM",
        action="REVIEW",
        category="medical_term",
        raw="五回声",
        converted="无回声",
        start=10,
        end=13,
    )
    auto = RuleDecision(
        rule_id="BS_REMARK",
        rule_version="V1",
        step_code="BUSINESS_SEGMENT",
        action="AUTO",
        category="medical_data",
        raw="五回声",
        converted="无回声",
        start=10,
        end=13,
    )

    assert registry.register(review) is True
    assert registry.register(auto) is False
    assert registry.decisions == [review]


def test_block_replaces_existing_auto():
    registry = DecisionRegistry()
    auto = RuleDecision(
        rule_id="A",
        rule_version="V1",
        step_code="NUMBER_NORMALIZE",
        action="AUTO",
        category="format",
        raw="abc",
        converted="ABC",
        start=0,
        end=3,
    )
    block = RuleDecision(
        rule_id="B",
        rule_version="V1",
        step_code="RISK_INTERCEPT",
        action="BLOCK",
        category="risk",
        raw="abc",
        converted=None,
        start=0,
        end=3,
    )

    assert registry.register(auto) is True
    assert registry.register(block) is True
    assert registry.decisions == [block]


def test_business_conversion_does_not_override_review():
    registry = DecisionRegistry()
    registry.register(
        RuleDecision(
            rule_id="C005",
            rule_version="V1",
            step_code="MEDICAL_TERM",
            action="REVIEW",
            category="medical_term",
            raw="五回声",
            converted="无回声",
            start=8,
            end=11,
        )
    )

    text, conversions = apply_business_segment_conversion(
        "左卵巢大小58×38五回声",
        decision_registry=registry,
    )

    assert "五回声" in text
    assert not any(
        item["raw"] == "五回声" and item["action"] == "AUTO"
        for item in conversions
    )


class TestPipelineOrchestrator:
    """Task 11：流水线编排器基本链路与结果分级。"""

    def test_run_pipeline_fixed_seven_steps(self):
        from app.services.conversion_pipeline.orchestrator import run_pipeline

        result = run_pipeline(
            raw_text="内膜9.2，右卵巢大小39×30，16.4。换边，左卵巢大小28×27，15.2。",
            config_hash="h1",
        )
        assert len(result.steps) == 7
        codes = [s.step_code for s in result.steps]
        assert codes == [
            "BASE_CLEANING", "NUMBER_NORMALIZE", "MEDICAL_TERM",
            "BUSINESS_SEGMENT", "FIELD_PARSE", "RUNTIME_RULE", "RISK_INTERCEPT",
        ]
        assert all(s.status == "success" for s in result.steps)
        assert all(s.step_name for s in result.steps)
        assert result.config_hash == "h1"
        assert result.result_level.value in ("AUTO_ACCEPT", "REVIEW_REQUIRED")

    def test_resolve_result_level_merges(self):
        from app.services.conversion_pipeline.orchestrator import resolve_result_level
        from app.services.conversion_pipeline.types import ResultLevel

        assert resolve_result_level([{"action": "BLOCK"}], []) == ResultLevel.MANUAL_AUDIO_REVIEW
        assert resolve_result_level([{"action": "REVIEW"}], []) == ResultLevel.REVIEW_REQUIRED
        assert resolve_result_level([], [{"action": "AUTO"}]) == ResultLevel.AUTO_ACCEPT
        assert resolve_result_level([], [{"action": "CANDIDATE"}]) == ResultLevel.REVIEW_REQUIRED

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
    # V14：医学词标准化提到最前，先保护“五回声”等医学近音词不被数字处理吞掉。
    assert STEP_ORDER[StepCode.MEDICAL_TERM] == 10
    assert STEP_ORDER[StepCode.BASE_CLEANING] == 20
    assert STEP_ORDER[StepCode.NUMBER_NORMALIZE] == 30
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
            "MEDICAL_TERM", "BASE_CLEANING", "NUMBER_NORMALIZE",
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


class TestDimensionCandidatesPipeline:
    """P0-01：尺寸候选真正进入最终文本、conversions 与结果分级。"""

    def test_pipeline_applies_d001_to_final_text(self):
        from app.services.conversion_engine import run_conversion

        result = run_conversion("右卵巢大小四八乘一。四零")
        assert "右卵巢大小48×40" in result.normalized_text
        assert result.fields["right_ovary_size"] == "48×40"

    def test_pipeline_d002_changes_result_level(self):
        from app.services.conversion_engine import run_conversion

        result = run_conversion("左边二九.九乘一点二零")
        assert any(
            item.get("rule_id") == "D002"
            and item.get("converted") == "29×20"
            and item.get("action") == "REVIEW"
            for item in result.conversions
        )
        assert result.result_level.value == "REVIEW_REQUIRED"

    def test_pipeline_d003_blocks_incomplete_ovary_size(self):
        from app.services.conversion_engine import run_conversion

        result = run_conversion("左卵巢大小宽度零乘以三八")
        assert any(item.get("rule_id") == "D003" for item in result.conversions)
        assert result.result_level.value == "MANUAL_AUDIO_REVIEW"


class TestRuntimeRuleGrading:
    """P0-02：参数规则动作进入 conversions 与最终结果分级。"""

    def test_runtime_review_rule_sets_review_required(self):
        from app.services.conversion_engine import run_conversion

        review_rule = {
            "rule_code": "RT_REVIEW",
            "system_handler": "field_threshold",
            "condition_config": {
                "field_codes": ["right_ovary_size"],
                "value_mode": "any_dimension",
                "operator": "lt",
                "threshold": 40,
                "warning_code": "OVARY_BELOW_40",
            },
            "action": "REVIEW",
            "risk_level": "high",
            "enabled": True,
        }
        result = run_conversion(
            "右卵巢大小39×30，16.4",
            runtime_rules=[review_rule],
        )
        assert result.result_level.value == "REVIEW_REQUIRED"

    def test_runtime_block_rule_sets_manual_audio_review(self):
        from app.services.conversion_engine import run_conversion

        block_rule = {
            "rule_code": "RT_BLOCK",
            "system_handler": "field_threshold",
            "condition_config": {
                "field_codes": ["right_ovary_size"],
                "value_mode": "any_dimension",
                "operator": "lt",
                "threshold": 40,
                "warning_code": "OVARY_BELOW_40",
            },
            "action": "BLOCK",
            "risk_level": "highest",
            "enabled": True,
        }
        result = run_conversion(
            "右卵巢大小39×30，16.4",
            runtime_rules=[block_rule],
        )
        assert result.result_level.value == "MANUAL_AUDIO_REVIEW"
        assert result.risk_blocked is True


class TestPipelineFailFast:
    """P0-04：步骤失败即停，最终状态标记 failed。"""

    def test_pipeline_stops_after_failed_step(self, monkeypatch):
        import app.services.conversion_pipeline.orchestrator as orchestrator
        from app.services.conversion_pipeline.orchestrator import run_pipeline

        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(orchestrator, "apply_number_normalize", boom)
        result = run_pipeline(raw_text="测试文本")
        assert result.status == "failed"
        assert result.steps[-1].status == "failed"
        assert result.steps[-1].error_message == "boom"
        # V14：医学词步骤提前，NUMBER_NORMALIZE 是第 3 步（MEDICAL_TERM/BASE_CLEANING 成功后失败）
        assert len(result.steps) == 3


class TestParserStateTrace:
    """P0-06：字段解析器真实状态与变迁进入步骤快照。"""

    def test_pipeline_snapshot_exposes_real_parser_state(self):
        from app.services.conversion_pipeline.orchestrator import run_pipeline

        result = run_pipeline(
            raw_text="右卵巢大小39×30，16.4。换边，左卵巢大小28×27，15.2。",
            config_hash="h",
        )
        field_step = next(step for step in result.steps if step.step_code == "FIELD_PARSE")
        assert field_step.state_after["current_side"] == "LEFT"
        assert field_step.state_transitions
        assert any(
            item["trigger"] in ("侧别切换", "换边", "左卵巢", "右卵巢")
            for item in field_step.state_transitions
        )


class TestSpanMapIntegration:
    """P0-07：SpanMap 接入，字段 span 能映射回原始文本坐标。"""

    def test_pipeline_span_map_maps_final_span_to_raw_coordinates(self):
        from app.services.conversion_pipeline.orchestrator import run_pipeline

        result = run_pipeline(raw_text="右卵巢大小四八乘一。四零", config_hash="h")
        field_step = next(step for step in result.steps if step.step_code == "FIELD_PARSE")
        span = next(
            item for item in field_step.source_spans
            if item["field_code"] == "right_ovary_size"
        )
        assert result.raw_text[span["raw_start"]:span["raw_end"]] == "四八乘一。四零"
        assert span["raw_end"] - span["raw_start"] > span["end"] - span["start"]


class TestNoSuffixEndometriumReview:
    """P0-02：14.8A（无“型”）→ 内膜厚度 + 内膜类型候选，status=REVIEW。"""

    def test_pipeline_no_suffix_endometrium_pair_is_review_candidate(self):
        from app.services.conversion_engine import run_conversion

        result = run_conversion("十四点八A")  # 经数字步骤后为 14.8A
        assert result.fields["endometrium_thickness"] == 14.8
        assert result.fields["endometrium_type"] == "A型"
        status = result.fields.get("field_status") or {}
        assert status.get("endometrium_thickness") == "REVIEW"
        assert status.get("endometrium_type") == "REVIEW"
        assert result.result_level.value == "REVIEW_REQUIRED"
        assert any(
            item.get("rule_id") == "S012" and item.get("action") == "REVIEW"
            for item in result.conversions
        )

    def test_pipeline_suffix_endometrium_pair_is_auto(self):
        from app.services.conversion_engine import run_conversion

        result = run_conversion("一些对话，7.0A型")
        assert result.fields.get("endometrium_thickness") == 7.0
        assert result.fields.get("endometrium_type") == "A型"
        assert not any(
            item.get("rule_id") == "S012" and item.get("action") == "REVIEW"
            for item in result.conversions
        )


class TestRuleDiagnostics:
    """P1：每条规则的 called/hit 真实诊断随步骤快照返回。"""

    def _medical_diags(self, raw_text: str, scene: str = "卵泡监测B超"):
        from app.services.conversion_pipeline.orchestrator import run_pipeline

        result = run_pipeline(raw_text=raw_text, scene=scene)
        medical = next(step for step in result.steps if step.step_code == "MEDICAL_TERM")
        return result, [hit for hit in medical.rule_hits if hit.get("diagnostic")]

    def test_medical_step_unmatched_rule_is_called_with_reason(self):
        result, diags = self._medical_diags("内膜9.2")
        assert diags
        c001 = next(item for item in diags if item["rule_id"] == "C001")
        assert c001["configured"] is True
        assert c001["called"] is True
        assert c001["hit"] is False
        assert c001["reason"] and "文本未出现" in c001["reason"]
        # 诊断记录携带完整契约字段
        required = {
            "rule_id", "rule_name", "configured", "called", "hit", "action",
            "matched_text", "converted", "changed", "reason", "evidence", "risk_level",
        }
        assert required.issubset(c001.keys())

    def test_medical_step_scene_mismatched_rule_is_not_called(self):
        result, diags = self._medical_diags("内膜9.2", scene="卵泡监测B超")
        c008 = next(item for item in diags if item["rule_id"] == "C008")  # 取卵麻醉场景
        assert c008["configured"] is True
        assert c008["called"] is False
        assert c008["hit"] is False
        assert c008["reason"] and "场景不符" in c008["reason"]

    def test_medical_step_hit_rule_carries_action_and_changed(self):
        result, diags = self._medical_diags("面膜九点五，C型")
        c016 = next(item for item in diags if item["rule_id"] == "C016")
        assert c016["called"] is True
        assert c016["hit"] is True
        assert c016["action"] == "AUTO"
        assert c016["matched_text"] == "面膜"
        assert c016["converted"] == "内膜"
        assert c016["changed"] is True

    def test_every_step_exposes_diagnostics_and_required_keys(self):
        from app.services.conversion_pipeline.orchestrator import run_pipeline

        result = run_pipeline(raw_text="内膜9.2", scene="卵泡监测B超")
        required = {
            "rule_id", "rule_name", "configured", "called", "hit", "action",
            "matched_text", "converted", "changed", "reason", "evidence", "risk_level",
        }
        for step in result.steps:
            diags = [hit for hit in step.rule_hits if hit.get("diagnostic")]
            assert all(required.issubset(item.keys()) for item in diags)
        for code in (
            "MEDICAL_TERM", "BASE_CLEANING", "NUMBER_NORMALIZE",
            "BUSINESS_SEGMENT", "FIELD_PARSE", "RISK_INTERCEPT",
        ):
            step = next(s for s in result.steps if s.step_code == code)
            diags = [hit for hit in step.rule_hits if hit.get("diagnostic")]
            assert diags, code

    def test_runtime_rule_unsupported_handler_is_not_called(self):
        from app.services.conversion_pipeline.orchestrator import run_pipeline

        bad_rule = {
            "rule_code": "RT_BAD_HANDLER",
            "system_handler": "eval_arbitrary_code",
            "pattern": "x", "replacement": "y",
            "action": "AUTO", "risk_level": "medium", "enabled": True,
        }
        result = run_pipeline(
            raw_text="右卵巢大小39×30", scene="卵泡监测B超",
            runtime_rules=[bad_rule],
        )
        step = next(s for s in result.steps if s.step_code == "RUNTIME_RULE")
        diag = next(
            hit for hit in step.rule_hits
            if hit.get("diagnostic") and hit.get("rule_id") == "RT_BAD_HANDLER"
        )
        assert diag["configured"] is True
        assert diag["called"] is False
        assert diag["hit"] is False
        assert "白名单" in diag["reason"]

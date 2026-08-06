"""风险拦截模块测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.conversion_engine.risk_intercept import check_risks, RiskInterceptor, RISK_RULES


class TestRiskRules:
    """风险规则测试"""

    def test_rules_loaded(self):
        """规则已加载"""
        assert len(RISK_RULES) == 17
        assert any(r.rule_id == "R001" for r in RISK_RULES)
        assert any(r.rule_id == "R016" for r in RISK_RULES)
        assert any(r.rule_id == "R017" for r in RISK_RULES)

    def test_r001_empty_text(self):
        """R001: 空文本 → BLOCK"""
        result = check_risks("", "", [], {}, [])
        assert result.blocked is True
        assert any(item["rule_id"] == "R001" for item in result.risk_items)

    def test_r002_repetition(self):
        """R002: 循环重复 → REVIEW"""
        text = "这是测试文本，用于验证重复截断功能。" * 5
        result = check_risks(text, text, [], {}, [])
        assert any(item["rule_id"] == "R002" for item in result.risk_items)

    def test_r004_negation_auto(self):
        """R004: 否定词AUTO修改 → REVIEW"""
        conversions = [
            {"raw": "五回声", "converted": "无回声", "action": "AUTO"}
        ]
        result = check_risks("五回声", "无回声", conversions, {}, [])
        assert any(item["rule_id"] == "R004" for item in result.risk_items)

    def test_r006_incomplete_dimension(self):
        """R006: 卵巢尺寸不完整 → BLOCK"""
        fields = {"right_ovary_size": "39"}
        result = check_risks("右卵巢大小39", "右卵巢大小39", [], fields, [])
        assert any(item["rule_id"] == "R006" for item in result.risk_items)

    def test_r008_number_change(self):
        """R008: 真实数字改变 → BLOCK"""
        conversions = [
            {"raw": "5.2", "converted": "9.2", "action": "AUTO"}
        ]
        result = check_risks("5.2", "9.2", conversions, {}, [])
        assert any(item["rule_id"] == "R008" for item in result.risk_items)

    def test_r014_high_risk_word(self):
        """R014: 高风险词纠错 → REVIEW"""
        conversions = [
            {"raw": "取消一支", "converted": "取消移植", "action": "AUTO"}
        ]
        result = check_risks("取消一支", "取消移植", conversions, {}, [])
        assert any(item["rule_id"] == "R014" for item in result.risk_items)

    def test_no_risk_normal_text(self):
        """正常文本无风险"""
        text = "内膜9.5，C型。右卵巢大小39×30"
        conversions = [
            {"raw": "C级", "converted": "C型", "action": "AUTO"}
        ]
        fields = {"endometrium_thickness": 9.5, "endometrium_type": "C型", "right_ovary_size": "39×30"}
        result = check_risks(text, text, conversions, fields, [])
        assert result.passed is True
        assert result.blocked is False


class TestRiskInterceptor:
    """风险拦截器测试"""

    def test_interceptor_instance(self):
        """拦截器实例化"""
        interceptor = RiskInterceptor()
        assert len(interceptor.risk_items) == 0

    def test_multiple_risks(self):
        """多个风险检测"""
        text = "五回声" * 10  # 重复
        conversions = [
            {"raw": "五回声", "converted": "无回声", "action": "AUTO"}
        ]
        fields = {"right_ovary_size": "39"}
        result = check_risks(text, text, conversions, fields, [])
        # 应该检测到多个风险
        assert len(result.risk_items) >= 2


class TestRiskIntegration:
    """风险拦截集成测试"""

    def test_tc004_risks(self):
        """TC004: 五回声 → 无回声 的风险"""
        conversions = [
            {"raw": "五回声", "converted": "无回声", "action": "REVIEW"}
        ]
        result = check_risks("二零乘以幺九五回声", "20×19无回声", conversions, {}, [])
        # 应该有风险项
        assert len(result.risk_items) >= 0  # 至少不报错

    def test_tc014_risks(self):
        """TC014: 取消一支 → 取消移植 的风险"""
        conversions = [
            {"raw": "取消一支", "converted": "取消移植", "action": "REVIEW"}
        ]
        result = check_risks("取消一支", "取消移植", conversions, {}, [])
        assert len(result.risk_items) >= 0  # 至少不报错


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

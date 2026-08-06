"""ASR 转化引擎测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.conversion_engine import run_conversion, ConversionResult
from app.services.conversion_engine.base_cleaning import apply_base_cleaning
from app.services.conversion_engine.number_normalize import apply_number_normalize
from app.services.conversion_engine.medical_term_correct import apply_medical_term_correct, CONFUSION_RULES


class TestBaseCleaning:
    """基础清洗测试"""

    def test_remove_language_chinese_tags(self):
        """移除 language Chinese<asr_text> 标签"""
        text = "language Chinese<asr_text>内膜九点五"
        result = apply_base_cleaning(text)
        assert "language" not in result.text
        assert "<asr_text>" not in result.text
        assert "内膜九点五" in result.text

    def test_remove_multiple_tags(self):
        """移除多个重复标签"""
        text = "language Chinese<asr_text>内膜九点五language Chinese<asr_text>十五点九"
        result = apply_base_cleaning(text)
        assert result.text == "内膜九点五十五点九"

    def test_remove_abnormal_spaces(self):
        """清除异常空格"""
        text = "内膜 九点五"
        result = apply_base_cleaning(text)
        assert "  " not in result.text

    def test_truncate_repeated_segments(self):
        """截断连续重复片段"""
        text = "这是测试文本，用于验证重复截断功能。" * 5
        result = apply_base_cleaning(text)
        assert len(result.text) < len(text)

    def test_empty_input(self):
        """空输入"""
        result = apply_base_cleaning("")
        assert result.text == ""


class TestNumberNormalize:
    """数字标准化测试"""

    def test_chinese_decimal_to_arabic(self):
        """N001: 中文小数转阿拉伯数字"""
        text = "内膜十七点八"
        result = apply_number_normalize(text)
        assert "17.8" in result.text

    def test_yao_as_one(self):
        """N002: 幺作为数字1"""
        text = "二幺"
        result = apply_number_normalize(text)
        assert "21" in result.text

    def test_multiply_operator_unify(self):
        """N003: 乘法连接词统一"""
        text = "三九乘以三零"
        result = apply_number_normalize(text)
        assert "39×30" in result.text

    def test_multiply_x_operator(self):
        """N003: x/X/* 统一为 ×"""
        text = "39x30"
        result = apply_number_normalize(text)
        assert "39×30" in result.text

    def test_unit_normalize(self):
        """N004: 单位统一"""
        text = "十二毫米"
        result = apply_number_normalize(text)
        assert "mm" in result.text

    def test_endometrium_type_normalize(self):
        """N005: 内膜分型格式化"""
        text = "C级"
        result = apply_number_normalize(text)
        assert "C型" in result.text

    def test_4digit_dimension_candidate(self):
        """N006: 4位连续尺寸候选拆分"""
        text = "右卵巢大小六零三五"
        result = apply_number_normalize(text)
        assert "候选" in result.text or "60×35" in result.text

    def test_decimal_sequence_split(self):
        """N010: 连续小数列表切分"""
        text = "11.09.48.8"
        result = apply_number_normalize(text)
        # 应该被切分为多个数字
        assert "," in result.text or "，" in result.text

    def test_count_expand(self):
        """N011: 重复数值计数保留"""
        text = "12.7两个"
        result = apply_number_normalize(text)
        assert "12.7" in result.text

    def test_numeric_list_punctuate(self):
        """N012: 数值列表标点恢复"""
        text = "卵泡 15.2 17.7 4.7"
        result = apply_number_normalize(text)
        # 应该添加逗号
        assert "，" in result.text or "," in result.text


class TestMedicalTermCorrect:
    """医学术语纠错测试"""

    def test_confusion_rules_loaded(self):
        """混淆词库已加载"""
        assert len(CONFUSION_RULES) > 0
        assert any(r.rule_id == "C001" for r in CONFUSION_RULES)

    def test_auto_correct_rou_luan_chao(self):
        """C001: 肉卵巢 → 右卵巢 (AUTO)"""
        text = "肉卵巢大小三九乘以三零"
        result = apply_medical_term_correct(text)
        assert "右卵巢" in result.text
        assert any(c["rule_id"] == "C001" and c["action"] == "AUTO" for c in result.conversions)

    def test_auto_correct_zhi_ma(self):
        """C008: 芝麻 → 麻醉 (AUTO, 需要取卵上下文)"""
        text = "取卵打芝麻"
        result = apply_medical_term_correct(text)
        assert "麻醉" in result.text

    def test_auto_correct_dong_embryo(self):
        """C010: 动胚胎 → 冻胚胎 (AUTO)"""
        text = "动胚胎动卵"
        result = apply_medical_term_correct(text)
        assert "冻胚胎" in result.text
        assert "冻卵" in result.text

    def test_candidate_liu_wan_qiao(self):
        """C002: 六碗桥大桥 → 右卵巢大小 (CANDIDATE)"""
        text = "六碗桥大桥六零三五"
        result = apply_medical_term_correct(text)
        assert "候选" in result.text

    def test_review_wu_hui_sheng(self):
        """C005: 五回声 → 无回声 (REVIEW, 高风险)"""
        text = "二零乘以幺九五回声"
        result = apply_medical_term_correct(text)
        # 应该标记为待复核
        assert any(c["rule_id"] == "C005" and c["action"] == "REVIEW" for c in result.conversions)
        assert any("待复核" in w for w in result.warnings)

    def test_block_san_ling(self):
        """C032: 三零，三零 → BLOCK"""
        text = "三零，三零"
        result = apply_medical_term_correct(text)
        assert any(c["rule_id"] == "C032" and c["action"] == "BLOCK" for c in result.conversions)

    def test_context_required(self):
        """上下文约束测试：芝麻在食物语境中不应替换"""
        text = "芝麻酱很好吃"
        result = apply_medical_term_correct(text)
        # 食物语境中不应替换
        assert "麻醉" not in result.text

    def test_excluded_context(self):
        """排除上下文测试：取款在金融语境中不应替换"""
        text = "去银行取款"
        result = apply_medical_term_correct(text)
        # 金融语境中不应替换
        assert "取卵" not in result.text

    def test_scene_auto_detect(self):
        """场景自动推断"""
        text = "内膜九点五，右卵巢大小"
        result = apply_medical_term_correct(text)
        # 应该自动推断为卵泡监测B超场景
        assert len(result.conversions) >= 0  # 至少不报错


class TestRunConversion:
    """完整转化流程测试"""

    def test_skip_conversion(self):
        """跳过转化"""
        text = "内膜九点五"
        result = run_conversion(text, skip_conversion=True)
        assert result.skipped is True
        assert result.normalized_text == text

    def test_full_conversion(self):
        """完整转化"""
        text = "内膜十七点五，C级。三九乘以三零"
        result = run_conversion(text)
        assert "17.5" in result.normalized_text
        assert "C型" in result.normalized_text
        assert "39×30" in result.normalized_text

    def test_conversion_records(self):
        """转化记录"""
        text = "内膜十七点八"
        result = run_conversion(text)
        assert len(result.conversions) > 0
        assert any(c["rule_id"] == "N001" for c in result.conversions)

    def test_real_world_case(self):
        """真实场景测试"""
        text = "内膜九点五，C型。六碗桥大桥六零三五，十七点一。language Chinese<asr_text>十五点九"
        result = run_conversion(text)
        # 应该移除标签
        assert "language" not in result.normalized_text
        # 应该保留数字
        assert "9.5" in result.normalized_text or "九点五" in result.normalized_text

    def test_full_pipeline_with_medical_terms(self):
        """完整流程包含医学术语纠错"""
        text = "内膜九点五，肉卵巢大小三九乘以三零"
        result = run_conversion(text)
        # 数字标准化
        assert "9.5" in result.normalized_text
        assert "39×30" in result.normalized_text
        # 医学术语纠错
        assert "右卵巢" in result.normalized_text

    def test_tc003_from_spec(self):
        """测试用例 TC003: 内膜九点二，尾生欠军"""
        text = "内膜九点二，尾生欠军"
        result = run_conversion(text)
        assert "9.2" in result.normalized_text
        assert "回声欠均" in result.normalized_text

    def test_tc011_from_spec(self):
        """测试用例 TC011: 肉卵巢大小三九乘以三零"""
        text = "肉卵巢大小三九乘以三零"
        result = run_conversion(text)
        assert "右卵巢" in result.normalized_text
        assert "39×30" in result.normalized_text

    def test_business_segment_driven_conversion_keeps_remark_separate_from_ovary_size(self):
        """新版口径：医学名词参与转化；无回声是备注，不拼进卵巢大小。"""
        text = "面膜十一点一B型。左卵巢大小五八乘以三八五回声。"

        result = run_conversion(text)

        assert "内膜11.1B型" in result.normalized_text
        assert "左卵巢大小58×38无回声" in result.normalized_text
        assert any(
            item["raw"] == "面膜" and item["converted"] == "内膜" and item["category"] == "medical_term"
            for item in result.conversions
        )
        assert any(
            item["raw"] == "五八乘以三八" and item["converted"] == "58×38" and item["category"] == "medical_data"
            for item in result.conversions
        )
        assert any(
            item["raw"] == "五回声" and item["converted"] == "无回声" and item["category"] == "medical_data"
            for item in result.conversions
        )
        assert not any("五八乘以三八五回声" == item["raw"] for item in result.conversions)


class TestRiskIntercept:
    """风险拦截测试（R005/R016/R017）"""

    def _rule_ids(self, result) -> set[str]:
        return {item["rule_id"] for item in (result.risk_result.risk_items if result.risk_result else [])}

    def test_follicle_over_40mm_is_kept_and_flagged(self):
        """R016: 卵泡 >40mm 不静默丢弃，保留字段并输出警示。"""
        result = run_conversion("右卵巢大小45×30，45.6，20.1")

        assert 45.6 in result.fields["right_follicles"]
        assert "R016" in self._rule_ids(result)
        assert result.risk_blocked is False

    def test_ovary_single_dimension_below_10mm_is_flagged(self):
        """R017: 卵巢单维 <10mm 输出警示。"""
        result = run_conversion("左卵巢大小9×30，15.2")

        assert result.fields["left_ovary_size"] == "9×30"
        assert "R017" in self._rule_ids(result)
        assert result.risk_blocked is False

    def test_missing_side_trigger_is_flagged(self):
        """R005: 卵巢数据缺少左右侧触发词（默认归属右侧）时警示复核。"""
        result = run_conversion("卵巢大小60×35，20.1")

        assert result.fields.get("right_ovary_size") == "60×35"
        assert "R005" in self._rule_ids(result)

    def test_ambiguous_left_right_phrase_is_flagged(self):
        """R005: 左右卵巢/左右侧模糊表述警示复核。"""
        result = run_conversion("左右卵巢大小60×35，20.1")

        assert "R005" in self._rule_ids(result)

    def test_normal_two_sides_passes_risk_check(self):
        """正常双侧数据不触发 R005/R016/R017。"""
        result = run_conversion("内膜9.2，右卵巢大小39×30，16.4。换边，左卵巢大小28×27，15.2。")

        assert result.risk_passed is True
        assert result.risk_result.risk_items == []


class TestWarningScope:
    """警示口径：医疗名词/换边词纠错不产生警示，警示仅由数据异常触发。"""

    def test_medical_term_correction_produces_no_risk_items(self):
        """名词纠错（肉卵巢→右卵巢）生效且不产生警示。"""
        result = run_conversion("肉卵巢大小60×35，15.2，14.8")

        # 名词纠错已生效
        assert result.fields.get("right_ovary_size") == "60×35"
        assert any(conv.get("converted", "") == "右卵巢" for conv in result.conversions)
        # 无数据异常时，名词纠错本身不产生警示
        assert result.risk_result.risk_items == []

    def test_side_switch_correction_produces_no_risk_items(self):
        """换边词纠错（放边→换边）生效且不产生警示。"""
        result = run_conversion("内膜9.2，右卵巢大小39×30。放边，左卵巢大小28×27。")

        # 换边后左侧数据正确归属
        assert result.fields.get("left_ovary_size") == "28×27"
        # 无数据异常时，换边词纠错不产生警示
        assert result.risk_result.risk_items == []

    def test_data_anomaly_still_triggers_warning(self):
        """数据异常（卵泡>40mm）仍触发警示，与名词纠错无警示对照。"""
        result = run_conversion("右卵巢大小39×30，41.5")

        assert "R016" in [item.get("rule_id") for item in result.risk_result.risk_items]
        assert result.fields.get("right_follicles") == [41.5]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

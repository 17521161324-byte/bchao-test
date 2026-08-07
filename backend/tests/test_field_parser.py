"""字段解析模块测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.conversion_engine.field_parser import parse_fields, FieldParser


class TestFieldParser:
    """字段解析器测试"""

    def test_parse_endometrium_thickness(self):
        """F001: 内膜厚度解析"""
        text = "内膜9.5"
        result = parse_fields(text)
        assert "endometrium_thickness" in result.fields
        assert result.fields["endometrium_thickness"] == 9.5

    def test_parse_endometrium_type(self):
        """F002/M003: 内膜类型解析（V14 仅在内膜业务窗口内解析标准 A/B/C 型）"""
        text = "内膜9.5，C型"
        result = parse_fields(text)
        assert "endometrium_type" in result.fields
        assert result.fields["endometrium_type"] == "C型"

    def test_parse_ovary_size_right(self):
        """F003: 右卵巢大小解析"""
        text = "右卵巢大小39×30"
        result = parse_fields(text)
        assert "right_ovary_size" in result.fields
        assert result.fields["right_ovary_size"] == "39×30"

    def test_parse_ovary_size_left(self):
        """F004: 左卵巢大小解析"""
        text = "左卵巢大小25×18"
        result = parse_fields(text)
        assert "left_ovary_size" in result.fields
        assert result.fields["left_ovary_size"] == "25×18"

    def test_side_switch(self):
        """F005/F006: 侧别切换"""
        parser = FieldParser()
        text = "右边39×30 换边 25×18"
        result = parser.parse(text)
        # 应该检测到侧别切换
        assert "right_ovary_size" in result.fields or "left_ovary_size" in result.fields

    def test_parse_follicles(self):
        """F007/F008: 卵泡列表解析"""
        text = "右卵巢大小39×30 12.5 15.2 8.7"
        result = parse_fields(text)
        assert "right_follicles" in result.fields
        assert isinstance(result.fields["right_follicles"], list)

    def test_parse_ultrasound_finding(self):
        """V14 F009: 超声描述（无回声/强回声等）归入备注，不冒充内膜类型"""
        text = "无回声"
        result = parse_fields(text)
        assert "ultrasound_findings" not in result.fields
        remark = str(result.fields.get("remark", ""))
        assert "无回声" in remark

    def test_parse_procedure(self):
        """F010: 操作信息解析"""
        text = "取卵"
        result = parse_fields(text)
        assert "procedure_info" in result.fields
        procedures = result.fields["procedure_info"]
        assert any(p["procedure"] == "取卵" for p in procedures)

    def test_parse_order(self):
        """F011: 医嘱解析"""
        text = "抽血"
        result = parse_fields(text)
        assert "followup_orders" in result.fields
        assert "抽血" in result.fields["followup_orders"]

    def test_full_text_parse(self):
        """完整文本解析"""
        text = "内膜9.5，C型。右卵巢大小39×30 12.5 15.2"
        result = parse_fields(text)
        assert "endometrium_thickness" in result.fields
        assert "endometrium_type" in result.fields
        assert "right_ovary_size" in result.fields
        assert "right_follicles" in result.fields

    def test_source_spans(self):
        """来源追踪"""
        text = "内膜9.5"
        result = parse_fields(text)
        assert len(result.source_spans) > 0
        assert result.source_spans[0]["field_code"] == "endometrium_thickness"

    def test_thickness_range_warning(self):
        """内膜厚度范围警告"""
        text = "内膜37"  # 超出 1-30mm 范围
        result = parse_fields(text)
        assert len(result.warnings) > 0
        assert "超出工程范围" in result.warnings[0]

    def test_empty_input(self):
        """空输入"""
        result = parse_fields("")
        assert result.fields == {}


class TestFieldParserIntegration:
    """字段解析器集成测试"""

    def test_tc001_fields(self):
        """TC001: 内膜9.5，C型。右卵巢大小"""
        text = "内膜9.5，C型。右卵巢大小39×30"
        result = parse_fields(text)
        assert result.fields.get("endometrium_thickness") == 9.5
        assert result.fields.get("endometrium_type") == "C型"
        assert result.fields.get("right_ovary_size") == "39×30"

    def test_tc011_fields(self):
        """TC011: 右卵巢大小39×30"""
        text = "右卵巢大小39×30"
        result = parse_fields(text)
        assert result.fields.get("right_ovary_size") == "39×30"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

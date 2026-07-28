"""测试 QwenASR._clean_text 清洗逻辑"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.asr import QwenASR


class TestCleanText:
    """_clean_text 方法测试"""

    def test_normal_text_unchanged(self):
        """正常文本保持不变"""
        text = "内膜九点五，C型。宛桥大桥六零三五"
        assert QwenASR._clean_text(text) == text

    def test_empty_input(self):
        """空输入返回空字符串"""
        assert QwenASR._clean_text("") == ""
        assert QwenASR._clean_text(None) == ""

    def test_language_chinese_prefix_with_asr_text_tag(self):
        """移除 language Chinese<asr_text> 组合模式"""
        text = "language Chinese<asr_text>内膜九点五"
        assert QwenASR._clean_text(text) == "内膜九点五"

    def test_multiple_language_chinese_asr_text_tags(self):
        """移除多个重复的 language Chinese<asr_text> 标签"""
        text = "language Chinese<asr_text>内膜九点五，C型。language Chinese<asr_text>十五点九"
        assert QwenASR._clean_text(text) == "内膜九点五，C型。十五点九"

    def test_asr_text_tag_with_closing(self):
        """提取 <asr_text>...</asr_text> 闭合标签内的内容"""
        text = "<asr_text>内膜九点五</asr_text>"
        assert QwenASR._clean_text(text) == "内膜九点五"

    def test_asr_text_tag_without_closing(self):
        """移除无闭合标签的 <asr_text>"""
        text = "<asr_text>内膜九点五"
        assert QwenASR._clean_text(text) == "内膜九点五"

    def test_language_chinese_prefix_only(self):
        """移除开头的 language Chinese 前缀"""
        text = "language Chinese:内膜九点五"
        assert QwenASR._clean_text(text) == "内膜九点五"

    case_insensitive_text = "LANGUAGE CHINESE<asr_text>内膜九点五"

    def test_case_insensitive(self):
        """大小写不敏感"""
        text = "LANGUAGE CHINESE<asr_text>内膜九点五"
        assert QwenASR._clean_text(text) == "内膜九点五"

    def test_various_delimiters(self):
        """支持冒号/空格等分隔符"""
        text = "language：Chinese：<asr_text>内膜九点五"
        assert QwenASR._clean_text(text) == "内膜九点五"

    def test_complex_real_world_case(self):
        """模拟真实 ASR A 输出（多段重复标签）"""
        text = (
            "language Chinese<asr_text>内膜九点五，C型。宛桥大桥六零三五，"
            "十七点一。language Chinese<asr_text>十五点九，十五点九，又一个，"
            "二十点一，十五点二。language Chinese<asr_text>十三点七"
        )
        expected = "内膜九点五，C型。宛桥大桥六零三五，十七点一。十五点九，十五点九，又一个，二十点一，十五点二。十三点七"
        assert QwenASR._clean_text(text) == expected

    def test_whitespace_handling(self):
        """处理首尾空白"""
        text = "  language Chinese<asr_text>内膜九点五  "
        assert QwenASR._clean_text(text) == "内膜九点五"

"""尺寸候选解析器测试（Task 5：D001/D002/D003）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.conversion_pipeline.dimension_parser import parse_dimension_candidates


def test_broken_multiply_word_auto_normalizes_in_ovary_context():
    result = parse_dimension_candidates("右卵巢大小四八乘一。四零")
    assert result[0].normalized == "48×40"
    assert result[0].action == "AUTO"


def test_broken_decimal_dimension_returns_review_candidate():
    result = parse_dimension_candidates("左边二九.九乘一点二零")
    assert result[0].normalized == "29×20"
    assert result[0].action == "REVIEW"
    assert result[0].warning_code == "DIMENSION_DECIMAL_RECONSTRUCTED"


def test_missing_first_dimension_uses_unknown_placeholder():
    result = parse_dimension_candidates("左卵巢大小宽度零乘以三八")
    assert result[0].normalized == "??×38"
    assert result[0].action == "REVIEW"


def test_plain_decimal_is_not_guessed_to_another_decimal():
    result = parse_dimension_candidates("左边四点八")
    assert all(item.normalized != "4.3" for item in result)

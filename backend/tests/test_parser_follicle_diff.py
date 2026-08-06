"""Tests for compare_follicle_details — 卵泡明细尺寸级/数量级差异对比。"""

import pytest

from app.services.parser import compare_follicle_details


def test_perfect_match_returns_no_diffs():
    identified = [{"size": 16.4, "count": 1}, {"size": 15.2, "count": 2}]
    ground_truth = [{"size": 15.2, "count": 2}, {"size": 16.4, "count": 1}]
    result = compare_follicle_details(identified, ground_truth)

    assert result["match"] is True
    assert result["identified"] == [{"size": 16.4, "count": 1}, {"size": 15.2, "count": 2}]
    assert result["truth"] == [{"size": 16.4, "count": 1}, {"size": 15.2, "count": 2}]
    assert result["identified_total"] == 3
    assert result["truth_total"] == 3
    assert result["missing"] == []
    assert result["extra"] == []
    assert result["count_mismatch"] == []
    assert result["possible_side_swaps"] == []
    assert result["summary"] == ""


def test_missing_size_reported():
    result = compare_follicle_details(
        [{"size": 16.0, "count": 1}],
        [{"size": 16.0, "count": 1}, {"size": 14.0, "count": 1}],
    )

    assert result["match"] is False
    assert result["missing"] == [{"size": 14.0, "count": 1}]
    assert result["extra"] == []
    assert result["count_mismatch"] == []
    assert result["summary"] == "缺失 14×1"


def test_extra_size_reported():
    result = compare_follicle_details(
        [{"size": 16.0, "count": 1}, {"size": 14.0, "count": 1}],
        [{"size": 16.0, "count": 1}],
    )

    assert result["match"] is False
    assert result["extra"] == [{"size": 14.0, "count": 1}]
    assert result["missing"] == []
    assert result["summary"] == "多余 14×1"


def test_count_mismatch_shows_size_and_direction():
    # 真实 16×2、抽取 16×1 → 16 少 1
    result = compare_follicle_details(
        [{"size": 16.0, "count": 1}],
        [{"size": 16.0, "count": 2}],
    )

    assert result["match"] is False
    assert result["count_mismatch"] == [
        {"size": 16.0, "identified_count": 1, "truth_count": 2, "diff": -1}
    ]
    assert result["summary"] == "16 少 1"

    # 反向：抽取 16×3、真实 16×2 → 16 多 1
    result = compare_follicle_details(
        [{"size": 16.0, "count": 3}],
        [{"size": 16.0, "count": 2}],
    )
    assert result["count_mismatch"][0]["diff"] == 1
    assert result["summary"] == "16 多 1"


def test_side_swap_detected_when_missing_in_opposite_side():
    # 右侧缺失 14，且左侧抽取结果中存在 14 → 疑似左右串边
    result = compare_follicle_details(
        [{"size": 16.0, "count": 1}],
        [{"size": 16.0, "count": 1}, {"size": 14.0, "count": 1}],
        opposite_identified=[{"size": 14.0, "count": 1}],
    )

    assert result["match"] is False
    assert result["possible_side_swaps"] == [{"size": 14.0, "count": 1, "opposite_count": 1}]
    assert result["missing"] == [{"size": 14.0, "count": 1}]
    assert result["summary"] == "缺失 14×1（疑似串边）"


def test_no_side_swap_when_missing_not_in_opposite():
    result = compare_follicle_details(
        [{"size": 16.0, "count": 1}],
        [{"size": 16.0, "count": 1}, {"size": 14.0, "count": 1}],
        opposite_identified=[{"size": 12.0, "count": 1}],
    )

    assert result["possible_side_swaps"] == []
    assert result["summary"] == "缺失 14×1"


def test_empty_inputs_match():
    assert compare_follicle_details([], [])["match"] is True
    assert compare_follicle_details(None, None)["match"] is True
    assert compare_follicle_details(None, [])["match"] is True
    assert compare_follicle_details([], None)["match"] is True


def test_invalid_inputs_are_ignored():
    result = compare_follicle_details(
        [{"size": "abc", "count": 1}, {"size": None, "count": 1}, {"size": 16.0, "count": 1}],
        [{"size": 16.0, "count": 1}],
    )
    assert result["match"] is True
    assert result["identified"] == [{"size": 16.0, "count": 1}]

    assert compare_follicle_details("not-a-list", "not-a-list")["match"] is True


def test_same_size_merged_across_entries():
    # 同尺寸多次出现应合并后比较
    result = compare_follicle_details(
        [{"size": 16.0, "count": 1}, {"size": 16.0, "count": 1}],
        [{"size": 16.0, "count": 2}],
    )
    assert result["match"] is True
    assert result["identified"] == [{"size": 16.0, "count": 2}]

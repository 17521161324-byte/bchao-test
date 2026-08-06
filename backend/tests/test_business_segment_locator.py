"""Tests for rule-based B-ultrasound business segment locator."""

from app.services.conversion_engine.business_segment_locator import locate_business_segments


def _by_type(segments, segment_type):
    return [item for item in segments if item["segment_type"] == segment_type]


def test_locates_narrow_medical_anchor_terms_only():
    text = "面膜6.3A型。右卵朝大小39×30，有无回声。卵泡12.1。"

    segments = locate_business_segments(text)
    anchors = _by_type(segments, "medical_term")

    assert [item["normalized"] for item in anchors] == ["内膜", "右卵巢"]
    assert all(item["text"] not in ("卵泡", "无回声") for item in anchors)


def test_locates_endometrium_values_without_global_number_noise():
    text = "陈一在说话。内膜6.3，A型。"

    segments = locate_business_segments(text)
    thickness = [item for item in segments if item["field_code"] == "endometrium_thickness"]
    etype = [item for item in segments if item["field_code"] == "endometrium_type"]
    numbers = [item for item in segments if item["text"] == "一"]

    assert thickness[0]["text"] == "6.3"
    assert thickness[0]["field_code"] == "endometrium_thickness"
    assert etype[0]["text"] == "A型"
    assert numbers == []


def test_locates_laterality_and_repairs_split_ovary_size_candidate():
    text = "右卵巢大小39×30，12.1，10.2。换边左卵巢大小48×1，29，13.5。"

    segments = locate_business_segments(text)
    laterality = _by_type(segments, "locator")
    ovary_sizes = [item for item in segments if item["field_code"].endswith("_ovary_size")]
    left_follicles = [item for item in segments if item["field_code"] == "left_follicles"]
    right_follicles = [item for item in segments if item["field_code"] == "right_follicles"]

    assert laterality[0]["text"] == "换边"
    assert any(item["field_code"] == "right_ovary_size" and item["normalized"] == "39×30" for item in ovary_sizes)
    assert any(item["field_code"] == "left_ovary_size" and item["normalized"] == "48×29" for item in ovary_sizes)
    assert [item["normalized"] for item in right_follicles] == [12.1, 10.2]
    assert [item["normalized"] for item in left_follicles] == [13.5]


def test_locates_chinese_decimal_and_chinese_ovary_size():
    text = "陈一说话。内膜九点五C型。右卵巢大小三九乘以三零，十七点一。换边左卵巢大小四八乘一，二九，十三点五。"

    segments = locate_business_segments(text)

    assert any(item["field_code"] == "endometrium_thickness" and item["normalized"] == 9.5 for item in segments)
    assert any(item["field_code"] == "right_ovary_size" and item["normalized"] == "39×30" for item in segments)
    assert any(item["field_code"] == "left_ovary_size" and item["normalized"] == "48×29" for item in segments)
    assert any(item["field_code"] == "right_follicles" and item["normalized"] == 17.1 for item in segments)
    assert any(item["field_code"] == "left_follicles" and item["normalized"] == 13.5 for item in segments)
    assert all(item["text"] != "一" for item in segments)


def test_locates_global_remark_values_and_noise():
    text = "嗯，好。左卵巢大小25×18，排精一次，左卵巢外无回声。"

    segments = locate_business_segments(text)
    remarks = [item for item in segments if item["field_code"] == "remark"]
    noise = _by_type(segments, "noise")

    assert {item["text"] for item in remarks} >= {"排精", "无回声"}
    assert {item["text"] for item in noise} >= {"嗯", "好"}


def test_segment_types_are_reduced_to_four_categories():
    text = "内膜九点五C型。右边右卵巢大小三九乘以三零，十七点一。无回声。嗯。"

    segments = locate_business_segments(text)

    assert {item["segment_type"] for item in segments} <= {"medical_term", "locator", "medical_data", "noise"}
    assert any(item["segment_type"] == "medical_data" and item["field_code"] == "right_follicles" for item in segments)
    assert any(item["segment_type"] == "medical_data" and item["field_code"] == "remark" for item in segments)


def test_ignores_colloquial_zhebian_and_keeps_late_same_side_follicles():
    text = (
        "面膜十一点一B型，我先包右边啊。"
        "右卵巢大小四五乘以二四，先抽血了吗？十四点四，十三点零，十一点一。"
        "这边声音小不？我知道，可以呀。"
        "医生和患者中间确认体位、裤子位置、探头方向、是否疼痛、屏幕显示和下一步操作，"
        "这段话很长但没有切换左右，也没有出现新的卵巢定位词。"
        "八点五，七点九，七点零。"
        "左卵巢大小四点五乘以幺九。"
    )

    segments = locate_business_segments(text)
    locators = _by_type(segments, "locator")
    right_follicles = [item for item in segments if item["field_code"] == "right_follicles"]

    assert all(item["text"] != "这边" for item in locators)
    assert {item["text"] for item in locators} == {"右边"}
    assert [item["normalized"] for item in right_follicles] == [14.4, 13.0, 11.1, 8.5, 7.9, 7.0]


def test_explicit_left_right_locator_can_anchor_ovary_data_without_ovary_term():
    text = (
        "内膜六点三A型。"
        "右边六幺乘以四十，十五点一，十五点一，十三点二。"
        "这些闲聊和确认不应该打断当前右侧归属。"
        "十四点六，十六点八，十七点五。"
        "左边十四点九，十六点八，十七点五，十五点七。"
    )

    segments = locate_business_segments(text)
    right_size = [item for item in segments if item["field_code"] == "right_ovary_size"]
    right_follicles = [item for item in segments if item["field_code"] == "right_follicles"]
    left_follicles = [item for item in segments if item["field_code"] == "left_follicles"]

    assert right_size[0]["normalized"] == "61×40"
    assert [item["normalized"] for item in right_follicles] == [15.1, 15.1, 13.2, 14.6, 16.8, 17.5]
    assert [item["normalized"] for item in left_follicles] == [14.9, 16.8, 17.5, 15.7]


def test_repeated_endometrium_does_not_block_explicit_right_locator_data():
    text = (
        "内膜六点三A型。原来内膜怎么样。"
        "右边四五乘以二一，通常看看形态来说，操作得好，内膜。"
        "十六点八，十三点五，十点六，十一点一，十四点五。"
        "左卵巢大小四八乘以幺九，十五点八，十五点一，十点五。"
    )

    segments = locate_business_segments(text)
    right_size = [item for item in segments if item["field_code"] == "right_ovary_size"]
    thickness = [item for item in segments if item["field_code"] == "endometrium_thickness"]
    right_follicles = [item for item in segments if item["field_code"] == "right_follicles"]
    left_follicles = [item for item in segments if item["field_code"] == "left_follicles"]

    assert [item["normalized"] for item in thickness] == [6.3]
    assert right_size[0]["normalized"] == "45×21"
    assert [item["normalized"] for item in right_follicles] == [16.8, 13.5, 10.6, 11.1, 14.5]
    assert [item["normalized"] for item in left_follicles] == [15.8, 15.1, 10.5]

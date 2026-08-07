from app.services.conversion_engine.context_inference import (
    collect_anonymous_ovary_groups,
    collect_fuzzy_ovary_inferences,
    collect_inferred_endometrium_pairs,
)


def test_id456_fuzzy_candidate_uses_later_left_anchor_to_infer_right():
    text = (
        "内膜9.5，C型。六宛桥大桥六零三五，17.1，15.9，15.9，20.1，15.2。"
        "换边，左卵巢大小37×30，18.2，13.1。"
    )
    rows = collect_fuzzy_ovary_inferences(text)
    row = next(item for item in rows if item.term == "六宛桥大桥")
    assert row.side == "RIGHT"
    assert row.target_field == "right_ovary_size"
    assert row.action == "REVIEW"


def test_id439_tubal_size_candidate_after_right_group_infers_left():
    text = (
        "内膜12.1，A型，右卵巢大小35×25，17.2，15.3，11.1，9.3，9.2，8.8。"
        "输卵管大小28×20，17.4，14.5，11.1。"
    )
    rows = collect_fuzzy_ovary_inferences(text)
    row = next(item for item in rows if item.term == "输卵管大小")
    assert row.side == "LEFT"
    assert row.target_field == "left_ovary_size"
    assert row.action == "REVIEW"


def test_id472_full_measurement_group_after_right_infers_left():
    text = (
        "右卵巢大小33×26，18.2，16.4，13.2。"
        "满朝大赏29×15，11.4，5.6，6.4。"
    )
    rows = collect_fuzzy_ovary_inferences(text)
    row = next(item for item in rows if item.term == "满朝大赏")
    assert row.side == "LEFT"
    assert row.rule_id in {"S011", "S006+S011"}


def test_id463_anonymous_measurement_group_before_left_is_right_segment():
    text = (
        "内膜14.8，A型。50×37，6.5，16.3，17.0，12.4，14.0，16.2，20.4，13.7，14.0。"
        "左卵巢大小38×25，18.0，19.7，17.0。"
    )
    groups = collect_anonymous_ovary_groups(text)
    assert len(groups) == 1
    assert groups[0].side == "RIGHT"
    assert groups[0].target_field == "right_ovary_size"
    assert groups[0].size_text == "50×37"


def test_endometrium_pair_without_anchor_is_inferred_before_ovary_segments():
    text = "一些普通对话，7.0A型，右卵巢大小35×25，17.2。"
    rows = collect_inferred_endometrium_pairs(text)
    assert len(rows) == 1
    assert rows[0].thickness == 7.0
    assert rows[0].endometrium_type == "A型"


def test_abc_pair_inside_ovary_segment_is_not_inferred_as_endometrium():
    text = "右卵巢大小35×25，17.2，7.0A型。"
    assert collect_inferred_endometrium_pairs(text) == []


def test_endometrium_pair_after_ovary_segment_in_separate_sentence_is_inferred():
    text = "右卵巢大小35×25，17.2。普通对话，8.6B型。左卵巢大小32×24，16.1。"
    rows = collect_inferred_endometrium_pairs(text)
    assert len(rows) == 1
    assert rows[0].thickness == 8.6
    assert rows[0].endometrium_type == "B型"


def test_endometrium_pair_in_same_sentence_as_ovary_anchor_is_not_inferred():
    text = "右卵巢大小35×25，17.2，8.6B型。"
    assert collect_inferred_endometrium_pairs(text) == []

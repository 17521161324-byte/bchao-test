from app.services.conversion_engine.medical_term_correct import apply_medical_term_correct


def run(text: str):
    return apply_medical_term_correct(text, scene="卵泡监测B超", rule_mode="builtin")


def test_endometrium_anchor_homophones_are_real_core_rules():
    first = run("面膜九点五，C型")
    second = run("内毛九点五，回声欠均")
    assert first.text.startswith("内膜九点五")
    assert second.text.startswith("内膜九点五")
    assert any(item.get("rule_id") == "C016" and item.get("action") == "AUTO" for item in first.conversions)
    assert any(item.get("rule_id") == "C017" and item.get("action") == "AUTO" for item in second.conversions)


def test_right_ear_outside_is_review_candidate_not_silent_rewrite():
    raw = "右耳朝外四零乘以幺四管状回声"
    result = run(raw)
    assert result.text == raw
    hit = next(item for item in result.conversions if item.get("rule_id") == "C037")
    assert hit["action"] == "REVIEW"
    assert hit["converted"] == "右卵巢外"


def test_stable_prefixed_right_ovary_outside_is_auto():
    result = run("前右卵巢外四零乘以幺四管状回声")
    assert result.text.startswith("右卵巢外")
    assert any(item.get("rule_id") == "C038" and item.get("action") == "AUTO" for item in result.conversions)


def test_echo_homophone_is_normalized_but_remains_description_semantics():
    result = run("内膜九点五，尾声欠均")
    assert "回声欠均" in result.text
    assert any(item.get("rule_id") == "C039" for item in result.conversions)

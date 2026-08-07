from app.services.conversion_engine.number_normalize import apply_number_normalize


def test_medical_five_echo_suffix_is_not_swallowed_by_dimension_conversion():
    result = apply_number_normalize("右卵巢内五八乘以三八五回声")
    assert result.text == "右卵巢内58×38五回声"
    assert "385" not in result.text


def test_four_digit_dimension_candidate_does_not_overwrite_effective_text():
    raw = "卵巢大小六零三五，17.1"
    result = apply_number_normalize(raw)
    assert result.text == raw
    candidate = next(item for item in result.conversions if item.get("rule_id") == "N006")
    assert candidate["converted"] == "60×35"
    assert candidate["action"] == "CANDIDATE"


def test_candidate_count_expansion_is_metadata_only():
    raw = "右卵巢大小35×25，12.7两个"
    result = apply_number_normalize(raw)
    assert "12.7两个" in result.text
    candidate = next(item for item in result.conversions if item.get("rule_id") == "N011")
    assert candidate["action"] == "CANDIDATE"


def test_endometrium_type_variant_is_normalized_only_in_endometrium_window():
    result = apply_number_normalize("内膜8.2，Ａ形，右卵巢大小35×25")
    assert "A型" in result.text
    assert "Ａ形" not in result.text
    hit = next(item for item in result.conversions if item.get("rule_id") == "N005")
    assert hit["action"] == "AUTO"


def test_type_like_text_outside_endometrium_window_is_not_rewritten():
    raw = "右卵巢大小35×25，A级资料另说"
    result = apply_number_normalize(raw)
    assert result.text == raw
    assert not any(item.get("rule_id") == "N005" for item in result.conversions)


def test_multiple_endometrium_types_are_not_silently_rewritten_by_n005():
    raw = "内膜9.0，B型啊A形，回声欠均"
    result = apply_number_normalize(raw)
    assert "A形" in result.text
    assert not any(item.get("rule_id") == "N005" for item in result.conversions)

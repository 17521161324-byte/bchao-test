from app.services.conversion_engine.number_normalize import apply_number_normalize
from app.services.conversion_engine import run_conversion


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


def test_four_digit_dimension_near_medical_ovary_anchor_generates_candidate():
    """P0-01：四位中文数字紧跟医学词步骤产出的卵巢大小锚点（六宛桥大桥）时，
    N006 读取上一步医学词候选元数据生成 60×35 尺寸候选，不改写正文。"""
    raw = "六宛桥大桥六零三五"
    result = apply_number_normalize(raw, ovary_anchor_raws=["六宛桥大桥"])
    assert result.text == raw  # 正文未被改写
    candidate = next(item for item in result.conversions if item.get("rule_id") == "N006")
    assert candidate["converted"] == "60×35"
    assert candidate["action"] == "CANDIDATE"
    assert candidate["start"] == len("六宛桥大桥")


def test_four_digit_dimension_without_anchor_metadata_stays_unchanged():
    """P0-01：没有医学词锚点元数据时，孤立四位数字不生成尺寸候选。"""
    raw = "六零三五"
    result = apply_number_normalize(raw)
    assert result.text == raw
    assert not any(item.get("rule_id") in ("N006", "N007") for item in result.conversions)


def test_pipeline_ovary_anchor_generates_dimension_candidate_without_rewriting():
    """P0-01：完整流水线（医学词步骤产出 OVARY_SIZE_ANCHOR 候选 → 数字步骤读元数据）
    生成 60×35 尺寸候选，正文与最终字段不受影响。"""
    result = run_conversion("六宛桥大桥六零三五")
    candidate = next(
        item for item in result.conversions
        if item.get("rule_id") == "N006" and item.get("converted") == "60×35"
    )
    assert candidate["action"] == "CANDIDATE"
    assert "六零三五" in result.normalized_text  # 正文未被改写
    assert not any(
        field in result.fields for field in ("right_ovary_size", "left_ovary_size")
    )


def test_pipeline_other_ovary_anchor_variants_also_generate_candidate():
    """P0-01：其他医学词锚点变体（六碗桥大桥/满朝大赏/图案朝大小/输卵管大小）同样生效，
    且业务代码不硬编码任何具体词（锚点串来自医学词步骤 conversions 元数据）。"""
    for anchor in ("六碗桥大桥", "满朝大赏", "图案朝大小", "输卵管大小"):
        result = run_conversion(f"{anchor}六零三五")
        candidate = next(
            item for item in result.conversions
            if item.get("rule_id") == "N006" and item.get("converted") == "60×35"
        )
        assert candidate["action"] == "CANDIDATE"
        assert "六零三五" in result.normalized_text


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

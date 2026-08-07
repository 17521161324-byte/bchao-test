from app.services.conversion_engine.endometrium_type_rules import collect_endometrium_type_rule_items


def test_explicit_c_type_is_m003_auto():
    items = collect_endometrium_type_rule_items("内膜9.5，C型，宫腔分离")
    hit = next(item for item in items if item.rule_id == "M003")
    assert hit.action == "AUTO"
    assert hit.converted == "C型"


def test_shape_and_fullwidth_are_normalized():
    items = collect_endometrium_type_rule_items("内膜8.2，Ａ形")
    hit = next(item for item in items if item.rule_id == "M003")
    assert hit.converted == "A型"


def test_type_is_not_searched_after_ovary_anchor():
    items = collect_endometrium_type_rule_items("内膜8.2，右卵巢大小35×25，A型")
    assert not any(item.rule_id in {"M003", "M006"} for item in items)


def test_multiple_complete_types_are_review_and_last_is_candidate():
    items = collect_endometrium_type_rule_items("内膜9.0，B型啊A型，回声欠均")
    hit = next(item for item in items if item.rule_id == "M006")
    assert hit.action == "REVIEW"
    assert hit.converted == "A型"
    assert "B型" in hit.raw and "A型" in hit.raw


def test_suspicious_homophone_is_review_without_guessing_type():
    items = collect_endometrium_type_rule_items("内膜9.0，飞行，回声欠均")
    hit = next(item for item in items if item.rule_id == "M007")
    assert hit.action == "REVIEW"
    assert hit.converted is None


def test_non_type_description_does_not_become_endometrium_type():
    items = collect_endometrium_type_rule_items("内膜16.7，回声欠均，内膜上见多个强回声包块")
    assert not any(item.rule_id in {"M003", "M006"} for item in items)

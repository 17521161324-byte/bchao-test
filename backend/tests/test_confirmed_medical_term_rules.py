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


def test_merge_strategy_core_first_db_dedup_and_override():
    """P1：CORE+DB 合并策略——先 CORE 再 DB；同 rule_id 只保留一个执行版本；
    与 CORE 行为一致的 DB 种子保持 CORE，行为不同的 DB 规则覆盖 CORE。"""
    from app.services.conversion_engine.medical_term_correct import (
        CONFUSION_RULES,
        merge_lexicon_rules,
    )

    db_identical = {
        "rule_id": "C001", "asr_error": "肉卵巢", "standard": "右卵巢",
        "scene": "卵泡监测B超", "required_context": "大小/尺寸/数值/左卵巢/换边",
        "excluded_context": "肉类", "match_type": "phonetic",
        "risk_level": "high", "action": "AUTO", "confidence": 0.95,
        "priority": 100, "enabled": True,
    }
    db_override = {
        "rule_id": "C002", "asr_error": "六碗桥大桥", "standard": "卵巢大小",
        "scene": "卵泡监测B超", "required_context": "内膜/卵泡/数字/左卵巢/右卵巢",
        "match_type": "phrase", "risk_level": "high", "action": "REVIEW",
        "priority": 100, "enabled": True,
    }
    db_new = {
        "rule_id": "C900", "asr_error": "测试词", "standard": "标准词",
        "scene": "卵泡监测B超", "action": "CANDIDATE", "priority": 100, "enabled": True,
    }

    merged = merge_lexicon_rules(CONFUSION_RULES, [db_identical, db_override, db_new])
    ids = [rule.rule_id for rule in merged]
    assert ids.count("C001") == 1
    assert ids.count("C002") == 1
    assert ids.count("C900") == 1
    c001 = next(rule for rule in merged if rule.rule_id == "C001")
    assert c001.action == "AUTO"  # 与 CORE 一致 → 系统核心保持 CORE
    c002 = next(rule for rule in merged if rule.rule_id == "C002")
    assert c002.action == "REVIEW"  # 与 CORE 不同 → DB 覆盖（仅一个版本）


def test_append_mode_db_override_changes_rule_behavior():
    """P1：append 模式下 DB 覆盖 CORE 的规则真实生效（如把 C002 由 CANDIDATE 改为 REVIEW）。"""
    override = {
        "rule_id": "C002", "asr_error": "六碗桥大桥", "standard": "卵巢大小",
        "scene": "卵泡监测B超", "required_context": "内膜/卵泡/数字/左卵巢/右卵巢",
        "match_type": "phrase", "risk_level": "high", "action": "REVIEW",
        "priority": 100, "enabled": True,
    }
    result = apply_medical_term_correct(
        "六碗桥大桥六零三五",
        scene="卵泡监测B超",
        rule_mode="append",
        extra_rules=[override],
    )
    hits = [item for item in result.conversions if item.get("rule_id") == "C002"]
    assert len(hits) == 1
    assert hits[0]["action"] == "REVIEW"


def test_append_mode_identical_db_seed_keeps_core_behavior():
    """P1：append 模式下与 CORE 完全一致的 DB 种子被丢弃，只保留一个 CORE 执行版本。"""
    duplicate = {
        "rule_id": "C016", "asr_error": "面膜", "standard": "内膜",
        "scene": "卵泡监测B超", "required_context": "点/A型/B型/C型/卵巢/回声",
        "match_type": "phonetic", "risk_level": "medium", "action": "AUTO",
        "confidence": 0.95, "priority": 100, "enabled": True,
    }
    result = apply_medical_term_correct(
        "面膜九点五",
        scene="卵泡监测B超",
        rule_mode="append",
        extra_rules=[duplicate],
    )
    hits = [item for item in result.conversions if item.get("rule_id") == "C016"]
    assert len(hits) == 1
    assert hits[0]["action"] == "AUTO"
    assert "内膜九点五" in result.text


def test_replace_mode_uses_db_rules_only():
    """P1：replace 模式下数据库规则完全替代硬编码。"""
    db_rule = {
        "rule_id": "R1", "asr_error": "面膜", "standard": "内膜",
        "scene": "卵泡监测B超", "action": "AUTO", "priority": 1, "enabled": True,
    }
    result = apply_medical_term_correct(
        "面膜九点五",
        scene="卵泡监测B超",
        rule_mode="replace",
        extra_rules=[db_rule],
    )
    assert "内膜九点五" in result.text
    assert len([item for item in result.conversions if item.get("rule_id") == "R1"]) == 1

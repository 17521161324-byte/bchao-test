"""Test Task 4: Task planning and invalidation rules."""
from app.services.experiment_planner import changed_stage, task_pairs


def test_llm_change_keeps_asr():
    before = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["x"]}
    after = {"asr_model_id": 1, "llm_model_id": 3, "prompt_template": "a", "hotwords": ["x"]}
    assert changed_stage(before, after) == "llm"


def test_prompt_change_keeps_asr():
    before = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["x"]}
    after = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "b", "hotwords": ["x"]}
    assert changed_stage(before, after) == "llm"


def test_hotword_change_invalidates_asr():
    before = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["x"]}
    after = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["y"]}
    assert changed_stage(before, after) == "asr"


def test_asr_model_change_invalidates_asr():
    before = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["x"]}
    after = {"asr_model_id": 2, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["x"]}
    assert changed_stage(before, after) == "asr"


def test_no_change_returns_none():
    before = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["x"]}
    after = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["x"]}
    assert changed_stage(before, after) is None


def test_task_pairs_are_cartesian_only_for_selected_combinations():
    assert task_pairs([10, 11], [20, 21]) == [(10, 20), (10, 21), (11, 20), (11, 21)]


def test_task_pairs_empty_patients():
    assert task_pairs([], [20, 21]) == []


def test_task_pairs_empty_combinations():
    assert task_pairs([10, 11], []) == []


def test_task_pairs_single():
    assert task_pairs([10], [20]) == [(10, 20)]


def test_hotwords_normalized_before_compare():
    """Hotwords in different order should be treated as same"""
    before = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["x", "y"]}
    after = {"asr_model_id": 1, "llm_model_id": 2, "prompt_template": "a", "hotwords": ["y", "x"]}
    assert changed_stage(before, after) is None

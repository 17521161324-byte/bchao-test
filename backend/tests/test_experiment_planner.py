"""Test Task 4: Task planning and invalidation rules."""
import pytest
import pytest_asyncio
from app.services.experiment_planner import changed_stage, task_pairs, plan_tasks, invalidate_tasks
from app.models.experiment import ExperimentBatch, ExperimentCombination, ExperimentTask, TaskStatus, TaskStage


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


@pytest.mark.anyio
async def test_plan_tasks_idempotent(db_session):
    """Test that planning tasks twice doesn't create duplicates"""
    batch = ExperimentBatch(name="Test Batch", selected_dates=["20260623"])
    db_session.add(batch)
    await db_session.flush()

    combo = ExperimentCombination(
        batch_id=batch.id,
        asr_model_id=1,
        prompt_template="{transcript}",
    )
    db_session.add(combo)
    await db_session.flush()

    patient_ids = [10, 11]

    tasks1 = await plan_tasks(db_session, batch.id, combo.id, patient_ids)
    tasks2 = await plan_tasks(db_session, batch.id, combo.id, patient_ids)

    assert len(tasks1) == 2
    assert len(tasks2) == 2

    task_ids = [t.id for t in tasks2]
    assert len(task_ids) == len(set(task_ids))


@pytest.mark.anyio
async def test_invalidate_asr_clears_all(db_session):
    """Test that ASR invalidation clears ASR+LLM+evaluation"""
    batch = ExperimentBatch(name="Test", selected_dates=[])
    db_session.add(batch)
    await db_session.flush()

    combo = ExperimentCombination(batch_id=batch.id, asr_model_id=1)
    db_session.add(combo)
    await db_session.flush()

    task = ExperimentTask(
        batch_id=batch.id,
        combination_id=combo.id,
        patient_id=10,
        stage=TaskStage.LLM.value,
        status=TaskStatus.SUCCESS.value,
        asr_results=[{"text": "test"}],
        full_transcript="test",
        structured_result={"right_follicle_total": 1},
        evaluation={"accuracy": 0.9},
    )
    db_session.add(task)
    await db_session.commit()

    count = await invalidate_tasks(db_session, combo.id, "asr")
    assert count == 1

    await db_session.refresh(task)
    assert task.asr_results == []
    assert task.full_transcript == ""
    assert task.structured_result is None
    assert task.evaluation is None
    assert task.stage == TaskStage.ASR.value
    assert task.status == TaskStatus.PENDING.value


@pytest.mark.anyio
async def test_invalidate_llm_keeps_asr(db_session):
    """Test that LLM invalidation keeps ASR transcript"""
    batch = ExperimentBatch(name="Test", selected_dates=[])
    db_session.add(batch)
    await db_session.flush()

    combo = ExperimentCombination(batch_id=batch.id, asr_model_id=1)
    db_session.add(combo)
    await db_session.flush()

    task = ExperimentTask(
        batch_id=batch.id,
        combination_id=combo.id,
        patient_id=10,
        stage=TaskStage.LLM.value,
        status=TaskStatus.SUCCESS.value,
        asr_results=[{"text": "preserved"}],
        full_transcript="preserved text",
        structured_result={"right_follicle_total": 1},
        evaluation={"accuracy": 0.9},
        llm_raw_output="raw",
    )
    db_session.add(task)
    await db_session.commit()

    count = await invalidate_tasks(db_session, combo.id, "llm")
    assert count == 1

    await db_session.refresh(task)
    assert task.full_transcript == "preserved text"
    assert task.structured_result is None
    assert task.evaluation is None
    assert task.stage == TaskStage.LLM.value
    assert task.status == TaskStatus.PENDING.value

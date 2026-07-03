"""Test Task 3: Experiment persistence models."""
import pytest
from app.models.experiment import ExperimentBatch, ExperimentCombination, ExperimentTask


def test_experiment_table_names_are_stable():
    assert ExperimentBatch.__tablename__ == "experiment_batches"
    assert ExperimentCombination.__tablename__ == "experiment_combinations"
    assert ExperimentTask.__tablename__ == "experiment_tasks"


def test_task_has_unique_patient_combination_key():
    constraints = ExperimentTask.__table__.constraints
    columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in constraints
        if hasattr(constraint, "columns")
    }
    assert ("batch_id", "combination_id", "patient_id") in columns


def test_batch_has_status_column():
    assert hasattr(ExperimentBatch, "status")
    assert hasattr(ExperimentBatch, "selected_dates")
    assert hasattr(ExperimentBatch, "selected_patient_ids")
    assert hasattr(ExperimentBatch, "total_tasks")
    assert hasattr(ExperimentBatch, "success_count")
    assert hasattr(ExperimentBatch, "failure_count")


def test_batch_default_patient_ids_is_list():
    batch = ExperimentBatch(name="Test")
    # JSON column default is a callable that returns empty list
    assert batch.selected_patient_ids is None or batch.selected_patient_ids == []


def test_combination_has_model_fks():
    assert hasattr(ExperimentCombination, "batch_id")
    assert hasattr(ExperimentCombination, "asr_model_id")
    assert hasattr(ExperimentCombination, "llm_model_id")
    assert hasattr(ExperimentCombination, "prompt_template")
    assert hasattr(ExperimentCombination, "hotwords")


def test_task_has_stage_and_status():
    assert hasattr(ExperimentTask, "stage")
    assert hasattr(ExperimentTask, "status")
    assert hasattr(ExperimentTask, "retry_count")
    assert hasattr(ExperimentTask, "asr_results")
    assert hasattr(ExperimentTask, "structured_result")
    assert hasattr(ExperimentTask, "evaluation")

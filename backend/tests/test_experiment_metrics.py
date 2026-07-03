"""Tests for experiment metrics."""
import pytest
from app.services.experiment_metrics import calculate_metrics
from app.models.experiment import ExperimentTask, TaskStatus


def test_metrics_no_score_or_rank():
    """Verify metrics don't include score/rank/best_combination"""
    tasks = []
    metrics = calculate_metrics(tasks)

    assert "score" not in metrics
    assert "rank" not in metrics
    assert "best_combination" not in metrics


def test_metrics_with_success_and_failure():
    """Test metrics calculation with mixed results"""
    tasks = [
        ExperimentTask(id=1, status=TaskStatus.SUCCESS.value, asr_results=[{"text": "a"}], full_transcript="a",
                      asr_duration=1.0, structured_result={"x": 1}, evaluation={"accuracy": 1.0}, accuracy=1.0, cost=0.5),
        ExperimentTask(id=2, status=TaskStatus.SUCCESS.value, asr_results=[{"text": "b"}], full_transcript="b",
                      asr_duration=2.0, structured_result={"x": 2}, evaluation={"accuracy": 0.9}, accuracy=0.9, cost=0.3),
        ExperimentTask(id=3, status=TaskStatus.FAILED.value, error_type="model_timeout"),
    ]

    metrics = calculate_metrics(tasks)
    assert metrics["total_tasks"] == 3
    assert metrics["success_count"] == 2
    assert metrics["failure_count"] == 1
    assert metrics["asr_success_rate"] == 2 / 3
    assert metrics["total_cost"] == 0.8

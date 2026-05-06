import pytest
from pydantic import ValidationError

from models.rca import RootCauseAnalysis
from models.task import ActionableTask, TaskPriority, TaskStatus
from models.anomaly import AnomalyResult


# ── RootCauseAnalysis ──────────────────────────────────────────────────────────

def test_rca_creation_with_required_fields():
    rca = RootCauseAnalysis(
        log_id="log-abc",
        summary="DB connection pool exhausted",
        root_cause="max_connections reached under high load",
        confidence=0.92,
    )
    assert rca.log_id == "log-abc"
    assert rca.confidence == 0.92
    assert rca.affected_services == []
    assert rca.suggested_fixes == []
    assert rca.trace_id is None


def test_rca_id_auto_generated():
    rca = RootCauseAnalysis(log_id="x", summary="s", root_cause="r", confidence=0.5)
    assert len(rca.id) == 36


def test_rca_confidence_rejects_above_one():
    with pytest.raises(ValidationError):
        RootCauseAnalysis(log_id="x", summary="s", root_cause="r", confidence=1.5)


def test_rca_confidence_rejects_below_zero():
    with pytest.raises(ValidationError):
        RootCauseAnalysis(log_id="x", summary="s", root_cause="r", confidence=-0.1)


def test_rca_with_services_and_fixes():
    rca = RootCauseAnalysis(
        log_id="log-1",
        summary="auth spike",
        root_cause="brute force attack",
        confidence=0.85,
        affected_services=["auth-service", "api-gateway"],
        suggested_fixes=["rate limit by IP", "enable account lockout"],
    )
    assert "auth-service" in rca.affected_services
    assert len(rca.suggested_fixes) == 2


# ── ActionableTask ─────────────────────────────────────────────────────────────

def test_task_creation_with_required_fields():
    task = ActionableTask(
        rca_id="rca-1",
        log_id="log-1",
        title="Fix connection pool",
        description="Increase max_connections in postgres config",
    )
    assert task.title == "Fix connection pool"
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.MEDIUM
    assert task.agent_id is None


def test_task_status_transitions():
    for status in ("pending", "approved", "in_progress", "resolved", "dismissed"):
        task = ActionableTask(
            rca_id="r", log_id="l", title="t", description="d",
            status=TaskStatus(status),
        )
        assert task.status.value == status


def test_task_priority_enum_values():
    for priority in ("low", "medium", "high", "critical"):
        task = ActionableTask(
            rca_id="r", log_id="l", title="t", description="d",
            priority=TaskPriority(priority),
        )
        assert task.priority.value == priority


def test_task_id_auto_generated():
    task = ActionableTask(rca_id="r", log_id="l", title="t", description="d")
    assert len(task.id) == 36


# ── AnomalyResult ──────────────────────────────────────────────────────────────

def test_anomaly_creation():
    anomaly = AnomalyResult(log_id="log-1", score=0.45, is_anomaly=True, threshold=0.72)
    assert anomaly.score == 0.45
    assert anomaly.is_anomaly is True
    assert anomaly.reviewed is False
    assert anomaly.threshold == 0.72


def test_anomaly_id_auto_generated():
    anomaly = AnomalyResult(log_id="x", score=0.5, is_anomaly=False, threshold=0.72)
    assert len(anomaly.id) == 36


def test_anomaly_score_rejects_above_one():
    with pytest.raises(ValidationError):
        AnomalyResult(log_id="x", score=1.5, is_anomaly=True, threshold=0.72)


def test_anomaly_score_rejects_below_zero():
    with pytest.raises(ValidationError):
        AnomalyResult(log_id="x", score=-0.1, is_anomaly=True, threshold=0.72)


def test_anomaly_threshold_rejects_above_one():
    with pytest.raises(ValidationError):
        AnomalyResult(log_id="x", score=0.5, is_anomaly=False, threshold=1.5)


def test_anomaly_threshold_rejects_below_zero():
    with pytest.raises(ValidationError):
        AnomalyResult(log_id="x", score=0.5, is_anomaly=False, threshold=-0.1)

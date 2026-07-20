"""Background task tracking (Milestone B, Step 6).

Thin CRUD helpers over the ``background_tasks`` table so long-running jobs
(ingestion, embedding, bulk export) can expose real status/progress to clients
polling ``GET /background-tasks/{id}``. Every helper is tenant-scoped and
defensive (they never raise on a missing task, so callers stay simple) and they
commit their own transaction so a caller can fire-and-forget.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from uuid import UUID

from app.models.all_models import BackgroundTask


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def create_task(
    db: Session,
    organization_id: Any,
    task_type: str,
    meta: Optional[Dict[str, Any]] = None,
) -> BackgroundTask:
    """Create a pending background task tracked for status polling."""
    task = BackgroundTask(
        organization_id=str(_uuid(organization_id)),
        data={
            "task_type": task_type,
            "status": "pending",
            "progress": 0,
            "result": {},
            **(meta or {}),
        },
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(
    db: Session, organization_id: Any, task_id: Any
) -> Optional[BackgroundTask]:
    """Fetch a task by id within the tenant (None if absent/foreign)."""
    return (
        db.query(BackgroundTask)
        .filter(
            BackgroundTask.id == _uuid(task_id),
            BackgroundTask.organization_id == _uuid(organization_id),
        )
        .first()
    )


def start_task(db: Session, task: BackgroundTask) -> BackgroundTask:
    task.status = "running"
    if task.started_at is None:
        task.started_at = _now()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_progress(
    db: Session, task: BackgroundTask, progress: int, status: Optional[str] = None
) -> BackgroundTask:
    """Update a task's percent-complete (clamped 0-100) and optional status."""
    task.progress = max(0, min(100, int(progress)))
    if status:
        task.status = status
    if task.status == "running" and task.started_at is None:
        task.started_at = _now()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def finish_task(
    db: Session, task: BackgroundTask, result: Optional[Dict[str, Any]] = None,
    status: str = "done",
) -> BackgroundTask:
    """Mark a task complete with optional result payload."""
    task.progress = 100
    task.status = status
    task.finished_at = _now()
    if result is not None:
        task.result = result
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def fail_task(db: Session, task: BackgroundTask, error: str) -> BackgroundTask:
    """Mark a task failed with an error message."""
    task.status = "failed"
    task.error = error
    task.finished_at = _now()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


__all__ = [
    "create_task",
    "get_task",
    "start_task",
    "update_progress",
    "finish_task",
    "fail_task",
]

# api/routes/tasks.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.postgres import append_audit_log, get_task_by_id, get_tasks, update_task_status
from models.task import ActionableTask, TaskStatus

router = APIRouter()

_DISMISSABLE_STATUSES = {TaskStatus.PENDING, TaskStatus.APPROVED}


class TasksResponse(BaseModel):
    tasks: list[ActionableTask]
    total: int


class TaskResponse(BaseModel):
    task: ActionableTask


@router.get("/tasks", response_model=TasksResponse)
async def list_tasks(
    request: Request,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> TasksResponse:
    results, total = await get_tasks(
        request.app.state.db_pool,
        status=status,
        priority=priority,
        limit=min(limit, 200),
        offset=offset,
    )
    return TasksResponse(tasks=results, total=total)


@router.post("/tasks/{task_id}/approve", response_model=TaskResponse)
async def approve_task(task_id: str, request: Request) -> TaskResponse:
    existing = await get_task_by_id(request.app.state.db_pool, task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    if existing.status != TaskStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"cannot approve task with status '{existing.status.value}'",
        )
    task = await update_task_status(request.app.state.db_pool, task_id, TaskStatus.APPROVED.value)
    await append_audit_log(
        request.app.state.db_pool, "task_approved", {"task_id": task_id}
    )
    return TaskResponse(task=task)


@router.post("/tasks/{task_id}/dismiss", response_model=TaskResponse)
async def dismiss_task(task_id: str, request: Request) -> TaskResponse:
    existing = await get_task_by_id(request.app.state.db_pool, task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    if existing.status not in _DISMISSABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"cannot dismiss task with status '{existing.status.value}'",
        )
    task = await update_task_status(request.app.state.db_pool, task_id, TaskStatus.DISMISSED.value)
    await append_audit_log(
        request.app.state.db_pool, "task_dismissed", {"task_id": task_id}
    )
    return TaskResponse(task=task)

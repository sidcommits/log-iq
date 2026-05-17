from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.postgres import append_audit_log, insert_rca
from intelligence.analyze import build_rca_context, create_tasks_from_rca, run_rca
from models.rca import RootCauseAnalysis
from models.task import ActionableTask

router = APIRouter()


class AnalyzeRequest(BaseModel):
    log_id: str
    create_tasks: bool = True


class AnalyzeResponse(BaseModel):
    rca: RootCauseAnalysis
    tasks: list[ActionableTask]


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_log(body: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    cfg = request.app.state.config
    try:
        context = await build_rca_context(
            log_id=body.log_id,
            pool=request.app.state.db_pool,
            openai_client=request.app.state.openai_client,
            qdrant_client=request.app.state.qdrant_client,
            config=cfg["rca"],
            collection=cfg["qdrant"].get("collection", "log_events"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        rca = await run_rca(context, request.app.state.llm_client, cfg["rca"])
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await insert_rca(request.app.state.db_pool, rca)
    await append_audit_log(
        request.app.state.db_pool, "rca_created", {"rca_id": rca.id, "log_id": body.log_id}
    )

    tasks: list[ActionableTask] = []
    if body.create_tasks:
        tasks = await create_tasks_from_rca(rca, request.app.state.db_pool)
        for task in tasks:
            await append_audit_log(
                request.app.state.db_pool, "task_created", {"task_id": task.id, "rca_id": rca.id}
            )

    return AnalyzeResponse(rca=rca, tasks=tasks)

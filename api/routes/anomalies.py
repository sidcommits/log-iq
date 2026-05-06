# api/routes/anomalies.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.postgres import append_audit_log, get_anomalies, mark_anomaly_reviewed
from models.anomaly import AnomalyResult

router = APIRouter()


class AnomaliesResponse(BaseModel):
    results: list[AnomalyResult]
    total: int


class ReviewResponse(BaseModel):
    anomaly: AnomalyResult


@router.get("/anomalies", response_model=AnomaliesResponse)
async def list_anomalies(
    request: Request,
    reviewed: bool | None = None,
    is_anomaly: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AnomaliesResponse:
    results, total = await get_anomalies(
        request.app.state.db_pool,
        reviewed=reviewed,
        is_anomaly=is_anomaly,
        limit=min(limit, 200),
        offset=offset,
    )
    return AnomaliesResponse(results=results, total=total)


@router.post("/anomalies/{anomaly_id}/review", response_model=ReviewResponse)
async def review_anomaly(anomaly_id: str, request: Request) -> ReviewResponse:
    anomaly = await mark_anomaly_reviewed(request.app.state.db_pool, anomaly_id)
    if anomaly is None:
        raise HTTPException(status_code=404, detail=f"anomaly {anomaly_id} not found")
    await append_audit_log(
        request.app.state.db_pool, "anomaly_reviewed", {"anomaly_id": anomaly_id}
    )
    return ReviewResponse(anomaly=anomaly)

# api/routes/correlate.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from intelligence.correlate import CorrelateResponse, correlate_trace

router = APIRouter()


@router.get("/correlate/{trace_id}", response_model=CorrelateResponse)
async def correlate(
    trace_id: str,
    request: Request,
    fresh_analysis: bool = False,
) -> CorrelateResponse:
    try:
        return await correlate_trace(
            trace_id=trace_id,
            fresh_analysis=fresh_analysis,
            pool=request.app.state.db_pool,
            openai_client=request.app.state.openai_client,
            qdrant_client=request.app.state.qdrant_client,
            anthropic_client=request.app.state.anthropic_client,
            config=request.app.state.config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

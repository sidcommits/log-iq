from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.postgres import append_audit_log
from intelligence.search import SearchFilters, SearchResponse, semantic_search

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    filters: SearchFilters | None = None
    limit: int = 20


@router.post("/search", response_model=SearchResponse)
async def search_logs(body: SearchRequest, request: Request) -> SearchResponse:
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")
    try:
        result = await asyncio.wait_for(
            semantic_search(
                query=body.query,
                filters=body.filters,
                limit=min(body.limit, 100),
                pool=request.app.state.db_pool,
                openai_client=request.app.state.openai_client,
                qdrant_client=request.app.state.qdrant_client,
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="search timed out")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    await append_audit_log(
        request.app.state.db_pool,
        "search_executed",
        {
            "query": body.query,
            "results": len(result.results),
            "fallback_used": result.fallback_used,
        },
    )
    return result

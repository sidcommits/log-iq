from __future__ import annotations

from datetime import datetime
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

from db.postgres import fetch_logs_by_ids, fetch_logs_by_text
from db.qdrant import search_vectors
from ingestion.pipeline import embed_texts
from models.log_event import LogEvent

_FALLBACK_THRESHOLD = 0.75


class SearchFilters(BaseModel):
    severity: str | None = None
    service: str | None = None
    environment: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class SearchResult(BaseModel):
    log: LogEvent
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    fallback_used: bool


def _build_qdrant_filter(filters: SearchFilters) -> Filter | None:
    conditions = []
    if filters.severity:
        conditions.append(FieldCondition(key="severity", match=MatchValue(value=filters.severity)))
    if filters.service:
        conditions.append(FieldCondition(key="service", match=MatchValue(value=filters.service)))
    if filters.environment:
        conditions.append(
            FieldCondition(key="environment", match=MatchValue(value=filters.environment))
        )
    if filters.start_time or filters.end_time:
        range_kwargs: dict[str, float] = {}
        if filters.start_time:
            range_kwargs["gte"] = filters.start_time.timestamp()
        if filters.end_time:
            range_kwargs["lte"] = filters.end_time.timestamp()
        conditions.append(FieldCondition(key="timestamp_unix", range=Range(**range_kwargs)))
    return Filter(must=conditions) if conditions else None


async def semantic_search(
    query: str,
    filters: SearchFilters | None,
    limit: int,
    pool: Any,
    openai_client: AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    collection: str = "log_events",
) -> SearchResponse:
    [query_vector] = await embed_texts(openai_client, [query])

    qdrant_filter = _build_qdrant_filter(filters) if filters else None
    hits = await search_vectors(
        qdrant_client, query_vector, qdrant_filter, limit=limit, collection=collection
    )

    if not hits or hits[0][1] < _FALLBACK_THRESHOLD:
        events = await fetch_logs_by_text(pool, query, limit)
        results = [SearchResult(log=e, score=0.0) for e in events]
        return SearchResponse(results=results, total=len(results), fallback_used=True)

    # Dedup by log_id — multiple chunks may match; keep highest score
    seen: dict[str, float] = {}
    for log_id, score in hits:
        if log_id not in seen or score > seen[log_id]:
            seen[log_id] = score

    events = await fetch_logs_by_ids(pool, list(seen.keys()))
    events_map = {e.id: e for e in events}

    results = sorted(
        [
            SearchResult(log=events_map[log_id], score=score)
            for log_id, score in seen.items()
            if log_id in events_map
        ],
        key=lambda r: r.score,
        reverse=True,
    )

    return SearchResponse(results=results[:limit], total=len(results), fallback_used=False)

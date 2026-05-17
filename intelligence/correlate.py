from __future__ import annotations

from openai import AsyncOpenAI
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient

from db.postgres import get_logs_by_trace_id, get_rca_by_log_ids
from intelligence.llm import LLMClient
from models.log_event import LogEvent
from models.rca import RootCauseAnalysis


class CorrelateResponse(BaseModel):
    logs_by_service: dict[str, list[LogEvent]]
    rca_records: list[RootCauseAnalysis]
    trace_summary: str | None = None


async def correlate_trace(
    trace_id: str,
    fresh_analysis: bool,
    pool,
    openai_client: AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    llm_client: LLMClient,
    config: dict,
) -> CorrelateResponse:
    max_logs = config.get("correlate", {}).get("max_trace_logs", 200)
    logs = await get_logs_by_trace_id(pool, trace_id, max_logs)
    if not logs:
        raise ValueError(f"no logs for trace_id {trace_id}")

    logs_by_service: dict[str, list[LogEvent]] = {}
    for log in logs:
        logs_by_service.setdefault(log.service, []).append(log)

    rca_records = await get_rca_by_log_ids(pool, [log.id for log in logs])

    trace_summary: str | None = None
    if fresh_analysis:
        services_text = "\n".join(
            f"## {svc} ({len(evts)} log(s))\n"
            + "\n".join(e.model_dump_json() for e in evts[:5])
            for svc, evts in logs_by_service.items()
        )
        prompt = (
            f"Analyse this distributed trace (trace_id: {trace_id}) spanning "
            f"{len(logs_by_service)} service(s). Return a concise summary of what happened, "
            f"the likely root cause, and which service is the origin of failure.\n\n"
            f"{services_text}"
        )
        rca_cfg = config.get("rca", {})
        trace_summary = await llm_client.complete(
            prompt=prompt,
            max_tokens=1024,
            timeout=rca_cfg.get("timeout_seconds", 30),
        )

    return CorrelateResponse(
        logs_by_service=logs_by_service,
        rca_records=rca_records,
        trace_summary=trace_summary,
    )

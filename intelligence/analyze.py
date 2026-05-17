# intelligence/analyze.py
from __future__ import annotations

import json
import re

from openai import AsyncOpenAI
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient

from db.postgres import fetch_logs_by_ids, get_logs_by_trace_id, insert_task
from db.qdrant import search_vectors
from ingestion.pipeline import embed_texts
from intelligence.llm import LLMClient
from models.log_event import LogEvent
from models.rca import RootCauseAnalysis
from models.task import ActionableTask, TaskPriority


class RCAContext(BaseModel):
    target: LogEvent
    semantic_neighbors: list[LogEvent] = []
    trace_logs: list[LogEvent] = []


def _build_prompt(context: RCAContext) -> str:
    schema = (
        '{"summary": str, "root_cause": str, "affected_services": list[str], '
        '"confidence": float (0-1), "suggested_fixes": list[str]}'
    )
    parts = [
        f"You are a log analysis expert. Analyse the following log event and return ONLY a JSON object matching this schema: {schema}\n\n",
        f"## Target Log\n{context.target.model_dump_json(indent=2)}\n",
    ]
    if context.semantic_neighbors:
        parts.append(
            "## Semantically Similar Logs\n"
            + "\n".join(e.model_dump_json(indent=2) for e in context.semantic_neighbors)
            + "\n"
        )
    if context.trace_logs:
        parts.append(
            f"## Trace Logs (trace_id: {context.target.trace_id})\n"
            + "\n".join(e.model_dump_json(indent=2) for e in context.trace_logs)
            + "\n"
        )
    return "".join(parts)


async def build_rca_context(
    log_id: str,
    pool,
    openai_client: AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    config: dict,
    collection: str = "log_events",
) -> RCAContext:
    events = await fetch_logs_by_ids(pool, [log_id])
    if not events:
        raise ValueError(f"log {log_id} not found")
    target = events[0]

    semantic_neighbors: list[LogEvent] = []
    if config.get("semantic_neighbors", True):
        k = config.get("max_semantic_k", 5)
        [vector] = await embed_texts(openai_client, [target.message])
        hits = await search_vectors(qdrant_client, vector, None, limit=k + 1, collection=collection)
        neighbor_ids = [lid for lid, _ in hits if lid != log_id][:k]
        if neighbor_ids:
            semantic_neighbors = await fetch_logs_by_ids(pool, neighbor_ids)

    trace_logs: list[LogEvent] = []
    if config.get("trace_logs", True) and target.trace_id:
        limit = config.get("max_trace_logs", 20)
        all_trace = await get_logs_by_trace_id(pool, target.trace_id, limit)
        trace_logs = [e for e in all_trace if e.id != log_id]

    return RCAContext(target=target, semantic_neighbors=semantic_neighbors, trace_logs=trace_logs)


async def run_rca(
    context: RCAContext,
    llm_client: LLMClient,
    config: dict,
) -> RootCauseAnalysis:
    prompt = _build_prompt(context)
    text = await llm_client.complete(
        prompt=prompt,
        max_tokens=2048,
        timeout=config.get("timeout_seconds", 30),
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise RuntimeError(f"Could not parse RCA response: {text[:200]}")
        data = json.loads(match.group())

    return RootCauseAnalysis(
        log_id=context.target.id,
        trace_id=context.target.trace_id,
        summary=data["summary"],
        root_cause=data["root_cause"],
        affected_services=data.get("affected_services", []),
        confidence=float(data["confidence"]),
        suggested_fixes=data.get("suggested_fixes", []),
    )


async def create_tasks_from_rca(
    rca: RootCauseAnalysis,
    pool,
) -> list[ActionableTask]:
    if rca.confidence >= 0.8:
        priority = TaskPriority.HIGH
    elif rca.confidence >= 0.5:
        priority = TaskPriority.MEDIUM
    else:
        priority = TaskPriority.LOW

    tasks = [
        ActionableTask(
            rca_id=rca.id,
            log_id=rca.log_id,
            title=fix[:120],
            description=fix,
            priority=priority,
        )
        for fix in rca.suggested_fixes
    ]
    for task in tasks:
        await insert_task(pool, task)
    return tasks

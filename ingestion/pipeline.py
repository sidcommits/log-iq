from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import tiktoken
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from db.postgres import fetch_unembedded_logs, mark_embedded
from db.qdrant import upsert_vectors
from models.log_event import LogEvent

logger = logging.getLogger(__name__)

_ENCODER = tiktoken.get_encoding("cl100k_base")
_MAX_TOKENS = 512
_BASE_BACKOFF = 1.0
_MAX_BACKOFF = 30.0


def chunk_message(text: str) -> list[str]:
    tokens = _ENCODER.encode(text)
    if len(tokens) <= _MAX_TOKENS:
        return [text]
    return [
        _ENCODER.decode(tokens[i : i + _MAX_TOKENS])
        for i in range(0, len(tokens), _MAX_TOKENS)
    ]


async def embed_texts(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


class IngestionWorker:
    def __init__(
        self,
        pool: Any,
        openai_client: AsyncOpenAI,
        qdrant_client: AsyncQdrantClient,
        poll_interval: float = 5.0,
        batch_size: int = 100,
        collection: str = "log_events",
    ) -> None:
        self._pool = pool
        self._openai = openai_client
        self._qdrant = qdrant_client
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._collection = collection
        self._task: asyncio.Task | None = None
        self._backoff = _BASE_BACKOFF

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            try:
                processed = await self._process_batch()
                self._backoff = _BASE_BACKOFF
                if not processed:
                    await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "IngestionWorker failure, retry in %.1fs: %s", self._backoff, exc
                )
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, _MAX_BACKOFF)

    async def _process_batch(self) -> bool:
        events = await fetch_unembedded_logs(self._pool, self._batch_size)
        if not events:
            return False

        # Build (event, chunk_index, chunk_text) tuples for all events
        items: list[tuple[LogEvent, int, str]] = [
            (event, i, chunk)
            for event in events
            for i, chunk in enumerate(chunk_message(event.message))
        ]

        # Embed all chunks in one API call
        embeddings = await embed_texts(self._openai, [text for _, _, text in items])

        # Count chunks per event to decide point ID strategy
        chunk_counts: dict[str, int] = {}
        for event, _, _ in items:
            chunk_counts[event.id] = chunk_counts.get(event.id, 0) + 1

        points: list[PointStruct] = [
            PointStruct(
                id=event.id if chunk_counts[event.id] == 1
                else str(uuid.uuid5(uuid.NAMESPACE_OID, f"{event.id}:{i}")),
                vector=embedding,
                payload={
                    "log_id": event.id,
                    "timestamp_unix": event.timestamp.timestamp(),
                    "severity": event.severity.value,
                    "service": event.service,
                    "environment": event.environment,
                    "trace_id": event.trace_id,
                },
            )
            for (event, i, _), embedding in zip(items, embeddings)
        ]

        await upsert_vectors(self._qdrant, points, self._collection)
        await mark_embedded(self._pool, [e.id for e in events])
        return True

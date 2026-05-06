from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from adapters.base import BaseSourceAdapter
from adapters.loki import LokiAdapter
from db import postgres as db
from models.log_event import LogEvent

logger = logging.getLogger(__name__)

_BASE_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
_MAX_FAILURES_BEFORE_CRITICAL = 10


class SourceWorker:
    def __init__(
        self,
        adapter: BaseSourceAdapter,
        pool: Any,
        mode: str,
        poll_interval: int = 30,
        stream_batch_size: int = 100,
        stream_flush_interval: float = 5.0,
    ) -> None:
        self._adapter = adapter
        self._pool = pool
        self._mode = mode
        self._poll_interval = poll_interval
        self._stream_batch_size = stream_batch_size
        self._stream_flush_interval = stream_flush_interval
        self._task: asyncio.Task | None = None
        self._backoff = _BASE_BACKOFF
        self._consecutive_failures = 0

    async def start(self) -> None:
        if self._mode == "poll":
            self._task = asyncio.create_task(self._poll_loop())
        else:
            self._task = asyncio.create_task(self._stream_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ── poll ──────────────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_once()
                self._reset_backoff()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._on_failure(exc)
                await asyncio.sleep(self._backoff)
                self._advance_backoff()
                continue
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        source = self._adapter.get_source_name()
        now = datetime.now(tz=timezone.utc)
        cursor = await db.get_cursor(self._pool, source)
        start = cursor if cursor is not None else now - timedelta(seconds=self._poll_interval)
        events = await self._adapter.fetch_logs(start=start, end=now)
        if events:
            await db.insert_logs(self._pool, events)
        await db.upsert_cursor(self._pool, source, now)

    # ── stream ────────────────────────────────────────────────────────────────

    async def _stream_loop(self) -> None:
        while True:
            try:
                await self._stream_once()
                self._reset_backoff()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._on_failure(exc)
                await asyncio.sleep(self._backoff)
                self._advance_backoff()

    async def _stream_once(self) -> None:
        buffer: list[LogEvent] = []
        aiter = self._adapter.stream_logs().__aiter__()
        while True:
            try:
                event = await asyncio.wait_for(
                    aiter.__anext__(), timeout=self._stream_flush_interval
                )
                buffer.append(event)
                if len(buffer) >= self._stream_batch_size:
                    await db.insert_logs(self._pool, buffer)
                    buffer.clear()
            except asyncio.TimeoutError:
                if buffer:
                    await db.insert_logs(self._pool, buffer)
                    buffer.clear()
            except StopAsyncIteration:
                if buffer:
                    await db.insert_logs(self._pool, buffer)
                return

    # ── backoff ───────────────────────────────────────────────────────────────

    def _on_failure(self, exc: Exception) -> None:
        self._consecutive_failures += 1
        level = (
            logging.CRITICAL
            if self._consecutive_failures >= _MAX_FAILURES_BEFORE_CRITICAL
            else logging.WARNING
        )
        logger.log(
            level,
            "Source %s: failure #%d, retry in %.1fs — %s",
            self._adapter.get_source_name(),
            self._consecutive_failures,
            self._backoff,
            exc,
        )

    def _reset_backoff(self) -> None:
        self._backoff = _BASE_BACKOFF
        self._consecutive_failures = 0

    def _advance_backoff(self) -> None:
        self._backoff = min(self._backoff * 2, _MAX_BACKOFF)


class SyncEngine:
    def __init__(self, config: dict, pool: Any) -> None:
        self._workers: list[SourceWorker] = [
            SourceWorker(
                adapter=_make_adapter(src),
                pool=pool,
                mode=src.get("mode", "poll"),
                poll_interval=src.get("poll_interval_seconds", 30),
            )
            for src in config.get("sources", [])
        ]

    async def start(self) -> None:
        for worker in self._workers:
            await worker.start()

    async def stop(self) -> None:
        for worker in self._workers:
            await worker.stop()


def _make_adapter(source_cfg: dict) -> BaseSourceAdapter:
    source_type = source_cfg["type"]
    if source_type == "loki":
        return LokiAdapter(url=source_cfg["url"], name=source_cfg["name"])
    raise ValueError(f"Unknown source type: {source_type!r}")

import json
from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import quote

import httpx
import websockets

from adapters.base import BaseSourceAdapter
from models.log_event import LogEvent, SeverityLevel


class LokiAdapter(BaseSourceAdapter):
    def __init__(
        self,
        url: str,
        name: str = "loki",
        query: str = '{environment="production"}',
    ) -> None:
        self._url = url.rstrip("/")
        self._name = name
        self._query = query

    def get_source_name(self) -> str:
        return self._name

    def normalise(self, raw: dict) -> LogEvent:
        severity_str = raw.get("severity", "UNKNOWN").upper()
        try:
            severity = SeverityLevel(severity_str)
        except ValueError:
            severity = SeverityLevel.UNKNOWN

        return LogEvent(
            timestamp=datetime.fromisoformat(raw["timestamp"]),
            severity=severity,
            service=raw.get("service", "unknown"),
            environment=raw.get("environment", "unknown"),
            trace_id=raw.get("trace_id"),
            span_id=raw.get("span_id"),
            message=raw["message"],
            metadata=raw.get("metadata", {}),
            raw=raw,
            source=self._name,
        )

    async def fetch_logs(
        self, start: datetime, end: datetime, limit: int = 100
    ) -> list[LogEvent]:
        start_ns = int(start.timestamp() * 1_000_000_000)
        end_ns = int(end.timestamp() * 1_000_000_000)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._url}/loki/api/v1/query_range",
                params={
                    "query": self._query,
                    "start": start_ns,
                    "end": end_ns,
                    "limit": limit,
                    "direction": "backward",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

        events: list[LogEvent] = []
        for stream in data.get("data", {}).get("result", []):
            for _ts, log_line in stream.get("values", []):
                try:
                    raw = json.loads(log_line)
                    events.append(self.normalise(raw))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
        return events

    def stream_logs(self) -> AsyncIterator[LogEvent]:
        raise NotImplementedError("implemented in Task 9")

    async def health_check(self) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._url}/ready", timeout=5.0)
                if resp.status_code == 200:
                    return {"status": "ok", "detail": "Loki is ready"}
                return {"status": "error", "detail": f"HTTP {resp.status_code}"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

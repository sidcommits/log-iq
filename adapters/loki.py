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
        raise NotImplementedError("implemented in Task 7")

    def stream_logs(self) -> AsyncIterator[LogEvent]:
        raise NotImplementedError("implemented in Task 9")

    async def health_check(self) -> dict:
        raise NotImplementedError("implemented in Task 8")

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from models.log_event import LogEvent


class BaseSourceAdapter(ABC):

    @abstractmethod
    async def fetch_logs(
        self, start: datetime, end: datetime, limit: int = 100
    ) -> list[LogEvent]:
        """Poll for logs between start and end. Returns up to limit events."""
        ...

    @abstractmethod
    def stream_logs(self) -> AsyncIterator[LogEvent]:
        """Real-time stream. Concrete implementations are async generators.
        Usage: async for event in adapter.stream_logs(): ..."""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """Check source availability. Returns {"status": "ok"|"error", "detail": str}."""
        ...

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the configured source name, e.g. "loki"."""
        ...

    @abstractmethod
    def normalise(self, raw: dict) -> LogEvent:
        """Convert a raw source log entry dict to a normalised LogEvent."""
        ...

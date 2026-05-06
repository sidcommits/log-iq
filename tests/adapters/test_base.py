import pytest
from adapters.base import BaseSourceAdapter


def test_base_adapter_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseSourceAdapter()


def test_partial_implementation_raises_on_instantiation():
    class OnlyName(BaseSourceAdapter):
        def get_source_name(self) -> str:
            return "partial"

    with pytest.raises(TypeError):
        OnlyName()


def test_full_implementation_instantiates_successfully():
    from datetime import datetime
    from collections.abc import AsyncIterator
    from models.log_event import LogEvent

    class StubAdapter(BaseSourceAdapter):
        async def fetch_logs(
            self, start: datetime, end: datetime, limit: int = 100
        ) -> list[LogEvent]:
            return []

        async def stream_logs(self) -> AsyncIterator[LogEvent]:
            return
            yield  # unreachable — marks this as an async generator

        async def health_check(self) -> dict:
            return {"status": "ok", "detail": "stub"}

        def get_source_name(self) -> str:
            return "stub"

        def normalise(self, raw: dict) -> LogEvent:
            raise NotImplementedError

    adapter = StubAdapter()
    assert adapter.get_source_name() == "stub"

from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def mock_lifespan_deps(monkeypatch):
    mock_pool = AsyncMock()
    mock_pool.close = AsyncMock()

    monkeypatch.setattr("api.main.init_pool", AsyncMock(return_value=mock_pool))
    monkeypatch.setattr("sync.engine.SyncEngine.start", AsyncMock())
    monkeypatch.setattr("sync.engine.SyncEngine.stop", AsyncMock())

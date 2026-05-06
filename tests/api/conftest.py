from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_lifespan_deps(monkeypatch):
    mock_pool = AsyncMock()
    mock_pool.close = AsyncMock()

    mock_qdrant = MagicMock()

    monkeypatch.setattr("api.main.init_pool", AsyncMock(return_value=mock_pool))
    monkeypatch.setattr("api.main.init_qdrant", AsyncMock(return_value=mock_qdrant))
    monkeypatch.setattr("api.main.ensure_collection", AsyncMock())
    monkeypatch.setattr("sync.engine.SyncEngine.start", AsyncMock())
    monkeypatch.setattr("sync.engine.SyncEngine.stop", AsyncMock())
    monkeypatch.setattr("ingestion.pipeline.IngestionWorker.start", AsyncMock())
    monkeypatch.setattr("ingestion.pipeline.IngestionWorker.stop", AsyncMock())

from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client.models import PointStruct

from db.qdrant import ensure_collection, search_vectors, upsert_vectors


@pytest.mark.asyncio
async def test_ensure_collection_creates_when_absent():
    client = AsyncMock()
    mock_response = MagicMock()
    mock_response.collections = []
    client.get_collections.return_value = mock_response

    await ensure_collection(client, "test_col")

    client.create_collection.assert_called_once()
    kwargs = client.create_collection.call_args.kwargs
    assert kwargs["collection_name"] == "test_col"


@pytest.mark.asyncio
async def test_ensure_collection_skips_when_present():
    client = AsyncMock()
    existing = MagicMock()
    existing.name = "log_events"
    mock_response = MagicMock()
    mock_response.collections = [existing]
    client.get_collections.return_value = mock_response

    await ensure_collection(client, "log_events")

    client.create_collection.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_vectors_calls_client_upsert():
    client = AsyncMock()
    points = [
        PointStruct(id="abc-123", vector=[0.1] * 1536, payload={"log_id": "abc-123"})
    ]

    await upsert_vectors(client, points, "log_events")

    client.upsert.assert_called_once_with(collection_name="log_events", points=points)


@pytest.mark.asyncio
async def test_upsert_vectors_skips_empty_list():
    client = AsyncMock()

    await upsert_vectors(client, [], "log_events")

    client.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_search_vectors_returns_log_ids_and_scores():
    client = AsyncMock()
    hit = MagicMock()
    hit.payload = {"log_id": "log-abc"}
    hit.score = 0.91
    client.search.return_value = [hit]

    results = await search_vectors(client, [0.1] * 1536, None, limit=5)

    assert results == [("log-abc", 0.91)]
    call_kwargs = client.search.call_args.kwargs
    assert call_kwargs["collection_name"] == "log_events"
    assert call_kwargs["limit"] == 5
    assert call_kwargs["with_payload"] is True


@pytest.mark.asyncio
async def test_search_vectors_returns_empty_when_no_hits():
    client = AsyncMock()
    client.search.return_value = []

    results = await search_vectors(client, [0.1] * 1536, None, limit=5)

    assert results == []

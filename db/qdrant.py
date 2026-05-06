from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, Filter, PointStruct, VectorParams

_COLLECTION = "log_events"
_VECTOR_SIZE = 1536


async def init_qdrant(host: str, port: int) -> AsyncQdrantClient:
    return AsyncQdrantClient(host=host, port=port)


async def ensure_collection(
    client: AsyncQdrantClient,
    collection: str = _COLLECTION,
) -> None:
    existing = await client.get_collections()
    names = {c.name for c in existing.collections}
    if collection not in names:
        await client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
        )


async def upsert_vectors(
    client: AsyncQdrantClient,
    points: list[PointStruct],
    collection: str = _COLLECTION,
) -> None:
    if not points:
        return
    await client.upsert(collection_name=collection, points=points)


async def search_vectors(
    client: AsyncQdrantClient,
    query_vector: list[float],
    qdrant_filter: Filter | None = None,
    limit: int = 20,
    score_threshold: float = 0.0,
    collection: str = _COLLECTION,
) -> list[tuple[str, float]]:
    """Returns [(log_id, score)] extracted from point payload, sorted by score desc."""
    hits = await client.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=limit,
        query_filter=qdrant_filter,
        score_threshold=score_threshold,
        with_payload=True,
    )
    return [(hit.payload["log_id"], hit.score) for hit in hits]

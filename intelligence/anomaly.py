from __future__ import annotations

from qdrant_client import AsyncQdrantClient

from db.qdrant import search_vectors
from models.anomaly import AnomalyResult
from models.log_event import LogEvent


async def score_batch(
    events: list[LogEvent],
    query_vectors: list[list[float]],
    qdrant_client: AsyncQdrantClient,
    config: dict,
    collection: str = "log_events",
) -> list[AnomalyResult]:
    if not events:
        return []

    k = config.get("knn_k", 10)
    threshold = config.get("threshold", 0.72)
    results: list[AnomalyResult] = []

    for event, vector in zip(events, query_vectors):
        hits = await search_vectors(qdrant_client, vector, None, limit=k + 1, collection=collection)
        neighbors = [(lid, score) for lid, score in hits if lid != event.id][:k]

        if not neighbors:
            avg_sim = 0.0
        else:
            avg_sim = sum(s for _, s in neighbors) / len(neighbors)

        results.append(
            AnomalyResult(
                log_id=event.id,
                score=round(1.0 - avg_sim, 6),
                is_anomaly=avg_sim < threshold,
                threshold=threshold,
            )
        )

    return results

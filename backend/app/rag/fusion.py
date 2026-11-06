from app.core.config import get_settings
from app.rag.types import RetrievedChunk


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    *,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    """Merge ranked lists with RRF and dedupe by qdrant_point_id."""
    settings = get_settings()
    k = settings.rrf_k
    limit = limit or settings.rerank_candidates

    scores: dict[str, float] = {}
    best: dict[str, RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            key = chunk.qdrant_point_id
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            existing = best.get(key)
            if existing is None or len(chunk.content) > len(existing.content):
                best[key] = chunk
            if existing is None and chunk.filename:
                best[key].filename = chunk.filename
            elif existing and not existing.filename and chunk.filename:
                best[key].filename = chunk.filename

    merged = []
    for key, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        chunk = best[key]
        chunk.score = score
        chunk.source = "fusion"
        merged.append(chunk)
        if len(merged) >= limit:
            break
    return merged

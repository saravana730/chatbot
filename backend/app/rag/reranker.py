import logging
from functools import lru_cache
from typing import Optional

from app.core.config import get_settings
from app.rag.types import RetrievedChunk

logger = logging.getLogger(__name__)


@lru_cache
def _get_reranker():
    from sentence_transformers import CrossEncoder

    settings = get_settings()
    logger.info("Loading reranker model %s", settings.reranker_model)
    return CrossEncoder(settings.reranker_model)


def rerank_chunks(
    query: str,
    candidates: list[RetrievedChunk],
    *,
    top_n: Optional[int] = None,
) -> list[RetrievedChunk]:
    settings = get_settings()
    n = top_n or settings.final_context_chunks
    if not candidates:
        return []

    if not settings.reranker_enabled:
        # Keep RRF order; avoid loading local CrossEncoder (OOM risk)
        out = candidates[:n]
        for chunk in out:
            chunk.source = "fusion"
        return out

    if len(candidates) == 1:
        candidates[0].source = "rerank"
        return candidates

    model = _get_reranker()
    pairs = [(query, c.content) for c in candidates]
    scores = model.predict(pairs)
    scored = list(zip(candidates, scores))
    scored.sort(key=lambda x: float(x[1]), reverse=True)

    out: list[RetrievedChunk] = []
    for chunk, score in scored[:n]:
        chunk.score = float(score)
        chunk.source = "rerank"
        out.append(chunk)
    return out

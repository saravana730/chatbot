from uuid import uuid4

from app.rag.fusion import reciprocal_rank_fusion
from app.rag.types import RetrievedChunk


def _chunk(pid: str, score: float, source: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=None,
        qdrant_point_id=pid,
        document_id=uuid4(),
        filename="a.pdf",
        page_number=1,
        chunk_index=0,
        content="text",
        score=score,
        source=source,
    )


def test_rrf_dedupes_and_ranks():
    a = _chunk("p1", 0.9, "semantic")
    b = _chunk("p2", 0.8, "semantic")
    c = _chunk("p1", 0.7, "bm25")
    merged = reciprocal_rank_fusion([[a, b], [c, b]], limit=10)
    ids = [m.qdrant_point_id for m in merged]
    assert ids.count("p1") == 1
    assert ids[0] == "p1"  # appears in both lists → higher RRF

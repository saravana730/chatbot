from typing import Optional
from uuid import UUID

from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.db.qdrant import get_qdrant_client
from app.ingestion.embedder import embed_texts
from app.rag.types import RetrievedChunk


def semantic_search(
    query: str,
    *,
    user_id: UUID,
    document_ids: Optional[list[UUID]] = None,
    top_k: Optional[int] = None,
) -> list[RetrievedChunk]:
    settings = get_settings()
    k = top_k or settings.semantic_top_k
    vector = embed_texts([query])[0]
    client = get_qdrant_client()

    must = [
        qmodels.FieldCondition(
            key="user_id",
            match=qmodels.MatchValue(value=str(user_id)),
        ),
        qmodels.FieldCondition(
            key="document_status",
            match=qmodels.MatchValue(value="ready"),
        ),
    ]
    if document_ids:
        must.append(
            qmodels.FieldCondition(
                key="document_id",
                match=qmodels.MatchAny(any=[str(d) for d in document_ids]),
            )
        )

    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        query_filter=qmodels.Filter(must=must),
        limit=k,
        with_payload=True,
    )

    chunks: list[RetrievedChunk] = []
    for hit in results:
        payload = hit.payload or {}
        chunks.append(
            RetrievedChunk(
                chunk_id=None,
                qdrant_point_id=str(hit.id),
                document_id=UUID(payload["document_id"]),
                filename="",
                page_number=payload.get("page_number"),
                chunk_index=int(payload.get("chunk_index", 0)),
                content=payload.get("text") or "",
                score=float(hit.score or 0.0),
                source="semantic",
            )
        )
    return chunks

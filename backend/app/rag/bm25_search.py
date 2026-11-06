from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.rag.types import RetrievedChunk


async def bm25_search(
    db: AsyncSession,
    query: str,
    *,
    user_id: UUID,
    document_ids: Optional[list[UUID]] = None,
    top_k: Optional[int] = None,
) -> list[RetrievedChunk]:
    """PostgreSQL full-text search as BM25 stand-in."""
    settings = get_settings()
    k = top_k or settings.bm25_top_k
    if not query.strip():
        return []

    params: dict = {
        "user_id": str(user_id),
        "query": query,
        "limit": k,
    }
    doc_filter = ""
    if document_ids:
        params["doc_ids"] = [str(d) for d in document_ids]
        doc_filter = "AND d.id = ANY(CAST(:doc_ids AS uuid[]))"

    sql = text(
        f"""
        SELECT
            c.id AS chunk_id,
            c.qdrant_point_id,
            c.document_id,
            d.filename,
            c.page_number,
            c.chunk_index,
            c.content,
            ts_rank_cd(c.search_vector, plainto_tsquery('english', :query)) AS rank
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.user_id = CAST(:user_id AS uuid)
          AND d.status = 'ready'
          AND c.search_vector @@ plainto_tsquery('english', :query)
          {doc_filter}
        ORDER BY rank DESC
        LIMIT :limit
        """
    )
    result = await db.execute(sql, params)
    rows = result.mappings().all()
    return [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            qdrant_point_id=row["qdrant_point_id"],
            document_id=row["document_id"],
            filename=row["filename"],
            page_number=row["page_number"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            score=float(row["rank"] or 0.0),
            source="bm25",
        )
        for row in rows
    ]

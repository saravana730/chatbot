import logging
import re
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.rag.bm25_search import bm25_search
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.reranker import rerank_chunks
from app.rag.semantic_search import semantic_search
from app.rag.types import RetrievedChunk, RetrievalResult

logger = logging.getLogger(__name__)

# Token-style @refs (no spaces). Spaced filenames are matched via known docs.
AT_REF_RE = re.compile(r"@([^\s@]+)")
FILE_EXT_RE = re.compile(
    r"@([^@\n]+?\.(?:pdf|png|jpe?g|tiff?|txt))",
    re.IGNORECASE,
)


def extract_at_references(text: str) -> list[str]:
    """Extract @mentions; prefer full filenames that include spaces + extension."""
    found: list[str] = []
    for m in FILE_EXT_RE.finditer(text or ""):
        name = m.group(1).strip()
        if name and name not in found:
            found.append(name)
    for m in AT_REF_RE.finditer(text or ""):
        name = m.group(1).strip()
        # Skip if already covered by a longer filename match
        if any(name == f or f.startswith(name) or name.startswith(f) for f in found):
            continue
        if name and name not in found:
            found.append(name)
    return found


def strip_at_mentions(text: str, filenames: Optional[list[str]] = None) -> str:
    """Remove @mentions so retrieval query is the real question."""
    out = text or ""
    names = sorted(filenames or [], key=len, reverse=True)
    for name in names:
        out = re.sub(re.escape("@" + name), " ", out, flags=re.IGNORECASE)
    out = FILE_EXT_RE.sub(" ", out)
    out = AT_REF_RE.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip()


async def resolve_document_scope(
    db: AsyncSession,
    user_id: UUID,
    message: str,
    explicit_ids: Optional[list[UUID]] = None,
) -> tuple[list[UUID], list[str]]:
    """Return (document_ids, matched_filenames)."""
    if explicit_ids:
        result = await db.execute(
            select(Document).where(
                Document.user_id == user_id,
                Document.id.in_(explicit_ids),
                Document.status == DocumentStatus.ready,
            )
        )
        docs = list(result.scalars().all())
        return [d.id for d in docs], [d.filename for d in docs]

    result = await db.execute(
        select(Document).where(
            Document.user_id == user_id,
            Document.status == DocumentStatus.ready,
        )
    )
    docs = list(result.scalars().all())
    if not docs:
        return [], []

    # Longest filename first so spaced names win over short tokens
    docs_sorted = sorted(docs, key=lambda d: len(d.filename), reverse=True)
    lower_msg = (message or "").lower()
    matched: list[Document] = []

    for doc in docs_sorted:
        fname = doc.filename.lower()
        stem = fname.rsplit(".", 1)[0]
        if f"@{fname}" in lower_msg or f"@{stem}" in lower_msg:
            matched.append(doc)

    if not matched:
        # Fallback: token @refs like @Policy.pdf
        for name in extract_at_references(message):
            needle = name.lower()
            for doc in docs_sorted:
                fname = doc.filename.lower()
                stem = fname.rsplit(".", 1)[0]
                if needle in {fname, stem} or fname.startswith(needle) or needle.startswith(stem):
                    if doc not in matched:
                        matched.append(doc)

    return [d.id for d in matched], [d.filename for d in matched]


async def enrich_filenames(
    db: AsyncSession, chunks: list[RetrievedChunk]
) -> list[RetrievedChunk]:
    missing = [c for c in chunks if not c.filename]
    if not missing:
        return chunks
    ids = {c.document_id for c in missing}
    result = await db.execute(select(Document).where(Document.id.in_(ids)))
    mapping = {d.id: d.filename for d in result.scalars().all()}
    for chunk in chunks:
        if not chunk.filename:
            chunk.filename = mapping.get(chunk.document_id, "document")
    return chunks


async def attach_chunk_ids(
    db: AsyncSession, chunks: list[RetrievedChunk]
) -> list[RetrievedChunk]:
    point_ids = [c.qdrant_point_id for c in chunks]
    if not point_ids:
        return chunks
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.qdrant_point_id.in_(point_ids))
    )
    by_point = {c.qdrant_point_id: c for c in result.scalars().all()}
    for chunk in chunks:
        row = by_point.get(chunk.qdrant_point_id)
        if row:
            chunk.chunk_id = row.id
            if not chunk.content:
                chunk.content = row.content
            if chunk.page_number is None:
                chunk.page_number = row.page_number
    return chunks


async def load_document_chunks(
    db: AsyncSession,
    document_ids: list[UUID],
    *,
    limit: int = 5,
    per_document: bool = False,
) -> list[RetrievedChunk]:
    """Fallback: take leading chunks from scoped documents (no vector filter).

    When per_document=True, take up to `limit` chunks from **each** document.
    Otherwise take `limit` chunks across the union (legacy behavior).
    """
    if not document_ids:
        return []
    if not per_document:
        result = await db.execute(
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(document_ids))
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(limit)
        )
        chunks: list[RetrievedChunk] = []
        for row, filename in result.all():
            chunks.append(
                RetrievedChunk(
                    chunk_id=row.id,
                    qdrant_point_id=row.qdrant_point_id or str(row.id),
                    document_id=row.document_id,
                    filename=filename,
                    page_number=row.page_number,
                    chunk_index=row.chunk_index,
                    content=row.content or "",
                    score=1.0,
                    source="document_fallback",
                )
            )
        return chunks

    chunks = []
    for doc_id in document_ids:
        result = await db.execute(
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id == doc_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(limit)
        )
        for row, filename in result.all():
            chunks.append(
                RetrievedChunk(
                    chunk_id=row.id,
                    qdrant_point_id=row.qdrant_point_id or str(row.id),
                    document_id=row.document_id,
                    filename=filename,
                    page_number=row.page_number,
                    chunk_index=row.chunk_index,
                    content=row.content or "",
                    score=1.0,
                    source="document_fallback",
                )
            )
    return chunks


async def hybrid_retrieve_per_document(
    db: AsyncSession,
    *,
    user_id: UUID,
    query: str,
    document_ids: list[UUID],
    scoped_filenames: Optional[list[str]] = None,
    per_doc_k: Optional[int] = None,
) -> RetrievalResult:
    """Balanced retrieval: top-k chunks from each document, then merge."""
    settings = get_settings()
    k = per_doc_k or settings.compare_per_doc_chunks
    names = list(scoped_filenames or [])
    if not document_ids:
        return RetrievalResult(
            chunks=[],
            insufficient=True,
            query_used=query,
            reason="No documents provided for per-document retrieval.",
            candidate_count=0,
            scoped_filenames=names,
        )

    merged: list[RetrievedChunk] = []
    for doc_id in document_ids:
        semantic = semantic_search(
            query, user_id=user_id, document_ids=[doc_id], top_k=max(k * 2, settings.semantic_top_k)
        )
        keyword = await bm25_search(
            db, query, user_id=user_id, document_ids=[doc_id], top_k=max(k * 2, settings.bm25_top_k)
        )
        fused = reciprocal_rank_fusion([semantic, keyword], limit=max(k * 2, 8))
        fused = await enrich_filenames(db, fused)
        fused = await attach_chunk_ids(db, fused)
        if not fused:
            fused = await load_document_chunks(db, [doc_id], limit=k, per_document=True)
        else:
            fused = rerank_chunks(query, fused, top_n=k)
        merged.extend(fused[:k])

    if not merged:
        return RetrievalResult(
            chunks=[],
            insufficient=True,
            query_used=query,
            reason="Per-document retrieval found no passages in the scoped files.",
            candidate_count=0,
            scoped_filenames=names,
        )

    return RetrievalResult(
        chunks=merged,
        insufficient=False,
        query_used=query,
        reason="ok",
        candidate_count=len(merged),
        scoped_filenames=names,
    )


async def hybrid_retrieve(
    db: AsyncSession,
    *,
    user_id: UUID,
    query: str,
    document_ids: Optional[list[UUID]] = None,
    scoped_filenames: Optional[list[str]] = None,
) -> RetrievalResult:
    settings = get_settings()
    scope = document_ids if document_ids else None
    names = list(scoped_filenames or [])

    semantic = semantic_search(
        query, user_id=user_id, document_ids=scope, top_k=settings.semantic_top_k
    )
    keyword = await bm25_search(
        db, query, user_id=user_id, document_ids=scope, top_k=settings.bm25_top_k
    )

    fused = reciprocal_rank_fusion(
        [semantic, keyword], limit=settings.rerank_candidates
    )
    fused = await enrich_filenames(db, fused)
    fused = await attach_chunk_ids(db, fused)
    candidate_count = len(fused)

    # Explicit @ scope with no vector/keyword hits → still use the document text
    if not fused and scope:
        fused = await load_document_chunks(
            db, scope, limit=settings.final_context_chunks
        )
        candidate_count = len(fused)
        if fused:
            return RetrievalResult(
                chunks=fused,
                insufficient=False,
                query_used=query,
                reason="Used document chunks after scoped search returned no hits.",
                candidate_count=candidate_count,
                scoped_filenames=names,
            )

    if not fused:
        reason = (
            "Retrieval ran (semantic + keyword) but found no matching passages"
            + (f" in {', '.join(names)}" if names else " across your ready documents")
            + "."
        )
        if scope and not names:
            reason = "Retrieval ran on the scoped file(s) but found no indexed chunks."
        return RetrievalResult(
            chunks=[],
            insufficient=True,
            query_used=query,
            reason=reason,
            candidate_count=0,
            scoped_filenames=names,
        )

    reranked = rerank_chunks(query, fused, top_n=settings.final_context_chunks)

    # Relevance threshold only applies to real similarity / reranker scores —
    # RRF fusion scores are ~1/(k+rank) and must not be compared to 0.2.
    if reranked and settings.reranker_enabled:
        top_score = reranked[0].score
        if 0.0 <= top_score <= 1.0 and top_score < settings.relevance_threshold:
            # Scoped asks: keep passages rather than hard-fail
            if scope:
                return RetrievalResult(
                    chunks=reranked,
                    insufficient=False,
                    query_used=query,
                    reason="Low relevance score; still using scoped document passages.",
                    candidate_count=candidate_count,
                    scoped_filenames=names,
                )
            return RetrievalResult(
                chunks=[],
                insufficient=True,
                query_used=query,
                reason=(
                    f"Retrieval found {candidate_count} passage(s), but the top "
                    f"relevance score ({top_score:.3f}) was below the threshold "
                    f"({settings.relevance_threshold})."
                ),
                candidate_count=candidate_count,
                scoped_filenames=names,
            )
        if top_score < -2.0:
            if scope:
                return RetrievalResult(
                    chunks=reranked,
                    insufficient=False,
                    query_used=query,
                    reason="Weak rerank scores; still using scoped document passages.",
                    candidate_count=candidate_count,
                    scoped_filenames=names,
                )
            return RetrievalResult(
                chunks=[],
                insufficient=True,
                query_used=query,
                reason=(
                    f"Retrieval found {candidate_count} passage(s), but rerank "
                    f"scores were too low (top={top_score:.3f})."
                ),
                candidate_count=candidate_count,
                scoped_filenames=names,
            )

    return RetrievalResult(
        chunks=reranked,
        insufficient=False,
        query_used=query,
        reason="ok",
        candidate_count=candidate_count,
        scoped_filenames=names,
    )


_STANDALONE_PREFIXES = (
    "summarize",
    "summary",
    "explain",
    "describe",
    "list ",
    "extract",
    "what is",
    "what are",
    "who is",
    "when is",
    "when does",
    "how much",
    "how many",
)


def maybe_rewrite_query(
    question: str,
    history: list[tuple[str, str]],
    *,
    scoped_filenames: list[str] | None = None,
    history_summary: str | None = None,
) -> str:
    """
    Light contextual rewrite for pronoun follow-ups only.
    Never rewrite when the user explicitly @scoped a file or asked a standalone question —
    that was causing prior-document contamination.
    """
    q = (question or "").strip()
    if not q:
        return q

    # New explicit document scope → use the question as-is
    if scoped_filenames:
        return q

    lower = q.lower()
    # Clear task on a (possibly new) topic — do not glue prior user turns
    if any(lower.startswith(p) or f" {p}" in f" {lower}" for p in _STANDALONE_PREFIXES):
        return q

    if not history and not history_summary:
        return q

    # Whole-word pronouns so "what about that?" counts as a follow-up
    if not re.search(
        r"\b(it|that|this|they|those|above)\b|\bthe (document|policy)\b",
        lower,
    ):
        return q

    last_user = next((c for r, c in reversed(history) if r == "user"), "")
    if last_user:
        return f"Given prior context: {last_user}\nFollow-up: {q}"
    if history_summary:
        return f"Given earlier conversation summary context.\nFollow-up: {q}"
    return q

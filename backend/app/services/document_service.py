import logging
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.qdrant import delete_document_points
from app.ingestion.validation import FileValidationError, sha256_hex, validate_upload
from app.models.document import (
    Document,
    DocumentChunk,
    DocumentFAQ,
    DocumentStatus,
    DocumentSummary,
    IngestionJob,
    JobStatus,
)
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()


class DocumentServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def enqueue_ingestion(document_id: UUID, job_id: UUID) -> None:
    redis = await create_pool(_redis_settings())
    try:
        await redis.enqueue_job("ingest_document", str(document_id), str(job_id))
    finally:
        await redis.close()


async def upload_document(
    db: AsyncSession,
    user: User,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> Document:
    try:
        file_type, _ = validate_upload(
            filename, content_type, data, settings.max_upload_bytes
        )
    except FileValidationError as exc:
        raise DocumentServiceError(exc.message, 400) from exc

    file_hash = sha256_hex(data)
    existing = await db.execute(
        select(Document).where(
            Document.user_id == user.id,
            Document.file_hash == file_hash,
        )
    )
    if existing.scalar_one_or_none():
        raise DocumentServiceError("Duplicate file already uploaded", 409)

    doc_id = uuid4()
    upload_root = Path(settings.upload_dir) / str(user.id) / str(doc_id)
    upload_root.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    storage_path = upload_root / safe_name
    storage_path.write_bytes(data)

    document = Document(
        id=doc_id,
        user_id=user.id,
        filename=safe_name,
        file_type=file_type,
        storage_path=str(storage_path),
        status=DocumentStatus.pending,
        file_hash=file_hash,
        progress_stage="queued",
        progress_detail="Waiting in the processing queue",
    )
    job = IngestionJob(document_id=doc_id, status=JobStatus.queued)
    db.add(document)
    db.add(job)
    await db.flush()

    try:
        await enqueue_ingestion(document.id, job.id)
    except Exception as exc:
        document.status = DocumentStatus.failed
        document.error_message = f"Failed to enqueue ingestion: {exc}"
        job.status = JobStatus.failed
        job.error = str(exc)
        logger.exception("Failed to enqueue ingestion for %s", document.id)

    return document


async def list_documents(db: AsyncSession, user: User) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_owned_document(
    db: AsyncSession, user: User, document_id: UUID
) -> Document:
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise DocumentServiceError("Document not found", 404)
    return document


async def get_document_status(
    db: AsyncSession, user: User, document_id: UUID
) -> tuple[Document, IngestionJob | None]:
    document = await get_owned_document(db, user, document_id)
    result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.document_id == document.id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    return document, job


async def get_summary(
    db: AsyncSession, user: User, document_id: UUID
) -> DocumentSummary:
    document = await get_owned_document(db, user, document_id)
    result = await db.execute(
        select(DocumentSummary).where(DocumentSummary.document_id == document.id)
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        raise DocumentServiceError("Summary not available yet", 404)
    return summary


async def get_faqs(
    db: AsyncSession, user: User, document_id: UUID
) -> list[DocumentFAQ]:
    document = await get_owned_document(db, user, document_id)
    result = await db.execute(
        select(DocumentFAQ)
        .where(DocumentFAQ.document_id == document.id)
        .order_by(DocumentFAQ.created_at.asc())
    )
    return list(result.scalars().all())


async def list_ready_documents(
    db: AsyncSession, user: User, *, limit: int = 5
) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(
            Document.user_id == user.id,
            Document.status == DocumentStatus.ready,
        )
        .order_by(Document.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_summaries_for_docs(
    db: AsyncSession,
    user: User,
    document_ids: list[UUID],
) -> list[tuple[Document, DocumentSummary | None]]:
    """Return (document, summary_or_none) for owned ready docs, preserving input order."""
    if not document_ids:
        return []
    result = await db.execute(
        select(Document).where(
            Document.user_id == user.id,
            Document.id.in_(document_ids),
            Document.status == DocumentStatus.ready,
        )
    )
    docs = {d.id: d for d in result.scalars().all()}
    sum_result = await db.execute(
        select(DocumentSummary).where(DocumentSummary.document_id.in_(document_ids))
    )
    summaries = {s.document_id: s for s in sum_result.scalars().all()}
    out: list[tuple[Document, DocumentSummary | None]] = []
    for doc_id in document_ids:
        doc = docs.get(doc_id)
        if doc is None:
            continue
        out.append((doc, summaries.get(doc_id)))
    return out


async def delete_document(db: AsyncSession, user: User, document_id: UUID) -> None:
    document = await get_owned_document(db, user, document_id)

    # Qdrant cleanup
    try:
        delete_document_points(document.id, user.id)
    except Exception:
        logger.exception("Failed to delete Qdrant points for %s", document.id)

    # Filesystem cleanup
    storage = Path(document.storage_path)
    parent = storage.parent
    try:
        if storage.exists():
            storage.unlink()
        if parent.exists() and parent.is_dir():
            shutil.rmtree(parent, ignore_errors=True)
    except Exception:
        logger.exception("Failed to delete files for %s", document.id)

    await db.execute(delete(Document).where(Document.id == document.id))
    await db.flush()


async def persist_chunks(
    db: AsyncSession,
    document_id: UUID,
    chunks: list[tuple[str, int | None, int, str]],
) -> None:
    """chunks: list of (content, page_number, chunk_index, qdrant_point_id)"""
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    for content, page_number, chunk_index, point_id in chunks:
        chunk = DocumentChunk(
            document_id=document_id,
            content=content,
            page_number=page_number,
            chunk_index=chunk_index,
            qdrant_point_id=point_id,
        )
        db.add(chunk)
    await db.flush()
    # Populate tsvector for future BM25
    await db.execute(
        text(
            """
            UPDATE document_chunks
            SET search_vector = to_tsvector('english', content)
            WHERE document_id = :doc_id
            """
        ),
        {"doc_id": str(document_id)},
    )

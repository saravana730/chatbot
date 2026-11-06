import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from arq.connections import RedisSettings
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.postgres import AsyncSessionLocal
from app.db.qdrant import build_point, upsert_chunks
from app.ingestion.chunker import chunk_document
from app.ingestion.embedder import embed_texts
from app.ingestion.normalizer import normalize_document
from app.ingestion.parser import parse_document
from app.ingestion.progress import compute_percent
from app.ingestion.summarizer import generate_faqs, hierarchical_summarize
from app.models.document import (
    Document,
    DocumentFAQ,
    DocumentStatus,
    DocumentSummary,
    IngestionJob,
    JobStatus,
)
from app.services.document_service import persist_chunks

logger = logging.getLogger(__name__)
settings = get_settings()


async def ingest_document(ctx, document_id: str, job_id: str) -> None:
    doc_uuid = UUID(document_id)
    job_uuid = UUID(job_id)
    async with AsyncSessionLocal() as session:
        try:
            await _run_pipeline(session, doc_uuid, job_uuid)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.exception("Ingestion failed for document %s", document_id)
            async with AsyncSessionLocal() as err_session:
                await _mark_failed(err_session, doc_uuid, job_uuid, str(exc))
                await err_session.commit()
            raise


async def _set_progress(
    session: AsyncSession,
    document: Document,
    stage: str,
    detail: str,
    *,
    current: int | None = None,
    total: int | None = None,
    percent: int | None = None,
) -> None:
    """Persist stage + unit/overall progress for the UI."""
    document.status = DocumentStatus.processing
    document.progress_stage = stage
    document.progress_detail = detail
    document.progress_current = current
    document.progress_total = total
    document.progress_percent = (
        percent
        if percent is not None
        else compute_percent(stage, current=current, total=total)
    )
    document.error_message = None
    await session.commit()
    await session.refresh(document)


async def _run_pipeline(session: AsyncSession, document_id: UUID, job_id: UUID) -> None:
    document = await session.get(Document, document_id)
    job = await session.get(IngestionJob, job_id)
    if document is None or job is None:
        raise RuntimeError("Document or job not found")

    now = datetime.now(timezone.utc)
    job.status = JobStatus.running
    job.started_at = now
    job.error = None
    await session.flush()
    await _set_progress(session, document, "starting", "Opening document…")

    document = await session.get(Document, document_id)
    job = await session.get(IngestionJob, job_id)
    assert document and job

    await _set_progress(
        session,
        document,
        "extracting",
        "Scanning pages…",
        current=0,
        total=None,
        percent=5,
    )
    document = await session.get(Document, document_id)
    extracted = await _parse_with_page_progress(session, document)

    page_count = len(extracted.pages) or 1
    await _set_progress(
        session,
        document,
        "normalizing",
        f"Cleaning text from {page_count} page{'s' if page_count != 1 else ''}…",
        current=page_count,
        total=page_count,
        percent=42,
    )
    document = await session.get(Document, document_id)
    normalized = normalize_document(extracted)
    full_text = normalized.full_text
    if not full_text.strip():
        raise RuntimeError("No text could be extracted from the document")

    approx_tokens = max(1, len(full_text) // 4)
    await _set_progress(
        session,
        document,
        "summarizing",
        f"Writing summary (~{approx_tokens} tokens)…",
        current=0,
        total=None,
        percent=45,
    )
    document = await session.get(Document, document_id)
    logger.info(
        "Summarizing document %s (%s chars, ~%s tokens)",
        document_id,
        len(full_text),
        approx_tokens,
    )

    async def _summary_progress(detail: str) -> None:
        doc = await session.get(Document, document_id)
        if not doc:
            return
        # Parse "section i/n" if present
        current = None
        total = None
        if "section" in detail.lower() and "/" in detail:
            try:
                part = detail.split("/")
                current = int("".join(ch for ch in part[0] if ch.isdigit()) or "0")
                total = int("".join(ch for ch in part[1] if ch.isdigit()) or "0")
            except ValueError:
                pass
        await _set_progress(
            session,
            doc,
            "summarizing",
            detail,
            current=current or None,
            total=total or None,
        )

    summary_text = await hierarchical_summarize(
        full_text, on_progress=_summary_progress
    )

    await session.execute(
        delete(DocumentSummary).where(DocumentSummary.document_id == document_id)
    )
    session.add(DocumentSummary(document_id=document_id, summary=summary_text))
    await session.flush()

    await _set_progress(
        session, document, "faqs", "Creating follow-up FAQs…", percent=74
    )
    document = await session.get(Document, document_id)
    faqs = await generate_faqs(summary_text)

    await session.execute(
        delete(DocumentFAQ).where(DocumentFAQ.document_id == document_id)
    )
    for faq in faqs:
        session.add(
            DocumentFAQ(
                document_id=document_id,
                question=faq["question"],
                answer=faq["answer"],
            )
        )
    await session.flush()

    await _set_progress(
        session, document, "chunking", "Splitting into searchable passages…", percent=80
    )
    document = await session.get(Document, document_id)
    text_chunks = chunk_document(normalized)
    if not text_chunks:
        raise RuntimeError("Chunking produced no chunks")

    n_chunks = len(text_chunks)
    await _set_progress(
        session,
        document,
        "embedding",
        f"Embedding passages 0 of {n_chunks}…",
        current=0,
        total=n_chunks,
    )
    document = await session.get(Document, document_id)

    # Embed in batches and report progress
    batch = max(1, settings.embedding_batch_size)
    vectors: list[list[float]] = []
    texts = [c.content for c in text_chunks]
    for start in range(0, n_chunks, batch):
        end = min(start + batch, n_chunks)
        vectors.extend(embed_texts(texts[start:end]))
        doc = await session.get(Document, document_id)
        if doc:
            await _set_progress(
                session,
                doc,
                "embedding",
                f"Embedding passages {end} of {n_chunks}…",
                current=end,
                total=n_chunks,
            )

    await _set_progress(
        session,
        document,
        "indexing",
        f"Indexing {n_chunks} passages…",
        current=n_chunks,
        total=n_chunks,
        percent=97,
    )
    document = await session.get(Document, document_id)
    points = []
    chunk_rows: list[tuple[str, int | None, int, str]] = []
    for chunk, vector in zip(text_chunks, vectors):
        point_id = str(uuid4())
        points.append(
            build_point(
                point_id,
                vector,
                user_id=document.user_id,
                document_id=document.id,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                document_status=DocumentStatus.ready.value,
                text=chunk.content,
            )
        )
        chunk_rows.append(
            (chunk.content, chunk.page_number, chunk.chunk_index, point_id)
        )

    upsert_chunks(points)
    await persist_chunks(session, document_id, chunk_rows)

    document = await session.get(Document, document_id)
    job = await session.get(IngestionJob, job_id)
    assert document and job
    document.status = DocumentStatus.ready
    document.progress_stage = "ready"
    document.progress_detail = f"Ready · {len(text_chunks)} chunks indexed"
    document.progress_current = page_count
    document.progress_total = page_count
    document.progress_percent = 100
    document.error_message = None
    job.status = JobStatus.completed
    job.completed_at = datetime.now(timezone.utc)
    job.error = None
    await session.flush()
    logger.info(
        "Ingestion completed for document %s (%d chunks)", document_id, len(text_chunks)
    )


async def _parse_with_page_progress(session: AsyncSession, document: Document):
    """Parse document while updating page progress after each PDF page."""
    from pathlib import Path

    import fitz

    from app.ingestion.pdf_extractor import _native_blocks, _ocr_page
    from app.ingestion.types import ExtractedDocument, ExtractedPage

    ft = (document.file_type or "").lower()
    if ft != "pdf":
        await _set_progress(
            session,
            document,
            "extracting" if ft == "txt" else "ocr",
            "Reading page 1 of 1…",
            current=1,
            total=1,
        )
        return parse_document(
            document.storage_path, document.filename, document.file_type
        )

    settings_local = get_settings()
    pdf = fitz.open(str(Path(document.storage_path)))
    pages: list[ExtractedPage] = []
    total = pdf.page_count
    try:
        for i, page in enumerate(pdf):
            page_number = i + 1
            await _set_progress(
                session,
                document,
                "extracting",
                f"Reading page {page_number} of {total}…",
                current=page_number,
                total=total,
            )
            document = await session.get(Document, document.id)
            assert document
            blocks = _native_blocks(page, page_number)
            native_text = "\n".join(b.text for b in blocks).strip()
            if len(native_text) >= settings_local.pdf_min_native_chars:
                pages.append(
                    ExtractedPage(
                        page_number=page_number, blocks=blocks, source="native"
                    )
                )
                continue
            await _set_progress(
                session,
                document,
                "ocr",
                f"OCR on page {page_number} of {total}…",
                current=page_number,
                total=total,
            )
            document = await session.get(Document, document.id)
            assert document
            ocr_blocks = _ocr_page(page, page_number)
            if ocr_blocks:
                source = "mixed" if native_text else "ocr"
                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        blocks=ocr_blocks if not native_text else blocks + ocr_blocks,
                        source=source,
                    )
                )
            else:
                pages.append(
                    ExtractedPage(
                        page_number=page_number, blocks=blocks, source="native"
                    )
                )
    finally:
        pdf.close()

    return ExtractedDocument(
        pages=pages, filename=document.filename, file_type="pdf"
    )


async def _mark_failed(
    session: AsyncSession, document_id: UUID, job_id: UUID, error: str
) -> None:
    document = await session.get(Document, document_id)
    job = await session.get(IngestionJob, job_id)
    if document:
        document.status = DocumentStatus.failed
        document.progress_stage = "failed"
        document.progress_detail = error[:500]
        document.error_message = error[:4000]
        document.progress_percent = document.progress_percent or 0
    if job:
        job.status = JobStatus.failed
        job.error = error[:4000]
        job.completed_at = datetime.now(timezone.utc)
    await session.flush()


class WorkerSettings:
    functions = [ingest_document]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 1
    job_timeout = 3600
    keep_result = 3600

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.dependencies import CurrentUser, DBSession, require_csrf
from app.schemas.document import (
    DocumentFAQOut,
    DocumentFAQsOut,
    DocumentOut,
    DocumentStatusOut,
    DocumentSummaryOut,
)
from app.services.document_service import (
    DocumentServiceError,
    delete_document,
    get_document_status,
    get_faqs,
    get_owned_document,
    get_summary,
    list_documents,
    upload_document,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _raise(exc: DocumentServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/upload", response_model=DocumentOut, dependencies=[Depends(require_csrf)])
async def upload(
    user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
) -> DocumentOut:
    data = await file.read()
    try:
        document = await upload_document(
            db, user, file.filename or "upload.bin", file.content_type, data
        )
    except DocumentServiceError as exc:
        _raise(exc)
    return DocumentOut.model_validate(document)


@router.get("", response_model=list[DocumentOut])
async def list_docs(user: CurrentUser, db: DBSession) -> list[DocumentOut]:
    docs = await list_documents(db, user)
    return [DocumentOut.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_doc(document_id: UUID, user: CurrentUser, db: DBSession) -> DocumentOut:
    try:
        document = await get_owned_document(db, user, document_id)
    except DocumentServiceError as exc:
        _raise(exc)
    return DocumentOut.model_validate(document)


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
async def status(document_id: UUID, user: CurrentUser, db: DBSession) -> DocumentStatusOut:
    try:
        document, job = await get_document_status(db, user, document_id)
    except DocumentServiceError as exc:
        _raise(exc)
    return DocumentStatusOut(
        document_id=document.id,
        status=document.status,
        job_status=job.status if job else None,
        progress_stage=document.progress_stage,
        progress_detail=document.progress_detail,
        progress_current=document.progress_current,
        progress_total=document.progress_total,
        progress_percent=document.progress_percent,
        error=(job.error if job and job.error else document.error_message),
        started_at=job.started_at if job else None,
        completed_at=job.completed_at if job else None,
    )


@router.get("/{document_id}/summary", response_model=DocumentSummaryOut)
async def summary(document_id: UUID, user: CurrentUser, db: DBSession) -> DocumentSummaryOut:
    try:
        row = await get_summary(db, user, document_id)
    except DocumentServiceError as exc:
        _raise(exc)
    return DocumentSummaryOut(
        document_id=row.document_id,
        summary=row.summary,
        created_at=row.created_at,
    )


@router.get("/{document_id}/faqs", response_model=DocumentFAQsOut)
async def faqs(document_id: UUID, user: CurrentUser, db: DBSession) -> DocumentFAQsOut:
    try:
        rows = await get_faqs(db, user, document_id)
    except DocumentServiceError as exc:
        _raise(exc)
    return DocumentFAQsOut(
        document_id=document_id,
        faqs=[DocumentFAQOut.model_validate(r) for r in rows],
    )


@router.delete("/{document_id}", dependencies=[Depends(require_csrf)])
async def remove(document_id: UUID, user: CurrentUser, db: DBSession) -> dict[str, str]:
    try:
        await delete_document(db, user, document_id)
    except DocumentServiceError as exc:
        _raise(exc)
    return {"detail": "Document deleted"}

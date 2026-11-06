from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import CurrentUser, DBSession, require_csrf
from app.schemas.session import (
    IngestBriefingOut,
    IngestBriefingRequest,
    MessageOut,
    SessionCreate,
    SessionOut,
)
from app.services.session_service import (
    SessionServiceError,
    create_session,
    delete_session,
    list_messages,
    list_sessions,
    post_ingest_briefing,
    post_ingest_briefing_to_latest,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _raise(exc: SessionServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("", response_model=SessionOut, dependencies=[Depends(require_csrf)])
async def create(user: CurrentUser, db: DBSession, body: SessionCreate | None = None) -> SessionOut:
    title = body.title if body else None
    session = await create_session(db, user, title)
    return SessionOut.model_validate(session)


@router.get("", response_model=list[SessionOut])
async def list_all(user: CurrentUser, db: DBSession) -> list[SessionOut]:
    sessions = await list_sessions(db, user)
    return [SessionOut.model_validate(s) for s in sessions]


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def messages(session_id: UUID, user: CurrentUser, db: DBSession) -> list[MessageOut]:
    try:
        rows = await list_messages(db, user, session_id)
    except SessionServiceError as exc:
        _raise(exc)
    return [MessageOut.model_validate(m) for m in rows]


@router.post(
    "/ingest-briefing",
    response_model=IngestBriefingOut,
    dependencies=[Depends(require_csrf)],
)
async def ingest_briefing_latest(
    body: IngestBriefingRequest,
    user: CurrentUser,
    db: DBSession,
) -> IngestBriefingOut:
    """Push summary + 2 FAQs into the user's most recently active chat session."""
    try:
        session, msg = await post_ingest_briefing_to_latest(db, user, body.document_id)
    except SessionServiceError as exc:
        _raise(exc)
    return IngestBriefingOut(
        session=SessionOut.model_validate(session),
        message=MessageOut.model_validate(msg),
    )


@router.post(
    "/{session_id}/ingest-briefing",
    response_model=MessageOut,
    dependencies=[Depends(require_csrf)],
)
async def ingest_briefing(
    session_id: UUID,
    body: IngestBriefingRequest,
    user: CurrentUser,
    db: DBSession,
) -> MessageOut:
    """Push document summary + two FAQs into a specific chat session."""
    try:
        msg = await post_ingest_briefing(db, user, session_id, body.document_id)
    except SessionServiceError as exc:
        _raise(exc)
    return MessageOut.model_validate(msg)


@router.delete("/{session_id}", dependencies=[Depends(require_csrf)])
async def remove(session_id: UUID, user: CurrentUser, db: DBSession) -> dict[str, str]:
    try:
        await delete_session(db, user, session_id)
    except SessionServiceError as exc:
        _raise(exc)
    return {"detail": "Session deleted"}

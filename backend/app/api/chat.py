from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.dependencies import CurrentUser, require_csrf
from app.db.postgres import get_session_factory
from app.schemas.session import ChatRequest
from app.services.chat_service import stream_chat

router = APIRouter(prefix="/sessions", tags=["chat"])


@router.post("/{session_id}/chat", dependencies=[Depends(require_csrf)])
async def chat(
    session_id: UUID,
    body: ChatRequest,
    user: CurrentUser,
    request: Request,
) -> StreamingResponse:
    """SSE chat stream. Uses a dedicated DB session for the long-lived generator."""

    async def event_generator():
        factory = get_session_factory()
        async with factory() as db:
            try:
                async for event in stream_chat(
                    db,
                    user,
                    session_id,
                    body.message,
                    body.document_ids,
                ):
                    if await request.is_disconnected():
                        break
                    yield event
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

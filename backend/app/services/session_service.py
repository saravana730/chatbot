from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentFAQ, DocumentStatus, DocumentSummary
from app.models.session import ChatMessage, ChatSession
from app.models.user import User
from app.services.document_service import DocumentServiceError, get_owned_document


class SessionServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def create_session(
    db: AsyncSession, user: User, title: str | None = None
) -> ChatSession:
    session = ChatSession(user_id=user.id, title=(title or "New chat")[:255])
    db.add(session)
    await db.flush()
    return session


async def list_sessions(db: AsyncSession, user: User) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_or_create_latest_session(db: AsyncSession, user: User) -> ChatSession:
    """Most recently updated chat for the user, or a new one if none exist."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if session is not None:
        return session
    return await create_session(db, user)


async def post_ingest_briefing_to_latest(
    db: AsyncSession, user: User, document_id: UUID
) -> tuple[ChatSession, ChatMessage]:
    session = await get_or_create_latest_session(db, user)
    message = await post_ingest_briefing(db, user, session.id, document_id)
    await db.refresh(session)
    return session, message


async def get_owned_session(
    db: AsyncSession, user: User, session_id: UUID
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user.id
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise SessionServiceError("Session not found", 404)
    return session


async def list_messages(
    db: AsyncSession, user: User, session_id: UUID
) -> list[ChatMessage]:
    await get_owned_session(db, user, session_id)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())


async def delete_session(db: AsyncSession, user: User, session_id: UUID) -> None:
    session = await get_owned_session(db, user, session_id)
    await db.execute(delete(ChatSession).where(ChatSession.id == session.id))
    await db.flush()


def _is_ingest_brief(citations: Any) -> bool:
    if not isinstance(citations, list) or not citations:
        return False
    first = citations[0]
    return isinstance(first, dict) and first.get("kind") == "ingest_brief"


async def load_history_pairs(
    db: AsyncSession, session_id: UUID, limit_turns: int
) -> list[tuple[str, str]]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit_turns * 4)
    )
    rows = list(reversed(result.scalars().all()))
    # Skip ingest briefings so they don't pollute retrieval / LLM history
    pairs = [
        (m.role, m.content)
        for m in rows
        if m.role in {"user", "assistant"} and not _is_ingest_brief(m.citations)
    ]
    return pairs[-(limit_turns * 2) :]


async def post_ingest_briefing(
    db: AsyncSession,
    user: User,
    session_id: UUID,
    document_id: UUID,
) -> ChatMessage:
    """Post summary + up to 2 FAQs into the chat when a document becomes ready."""
    session = await get_owned_session(db, user, session_id)
    try:
        document = await get_owned_document(db, user, document_id)
    except DocumentServiceError as exc:
        raise SessionServiceError(exc.message, exc.status_code) from exc

    if document.status != DocumentStatus.ready:
        raise SessionServiceError("Document is not ready yet", 409)

    # Idempotent: one briefing per document per session
    existing = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(40)
    )
    doc_key = str(document.id)
    for msg in existing.scalars().all():
        if not _is_ingest_brief(msg.citations):
            continue
        brief = msg.citations[0] if msg.citations else {}
        if str(brief.get("document_id")) == doc_key:
            return msg

    summary_row = (
        await db.execute(
            select(DocumentSummary).where(DocumentSummary.document_id == document.id)
        )
    ).scalar_one_or_none()
    if summary_row is None or not summary_row.summary.strip():
        raise SessionServiceError("Summary not available yet", 404)

    faq_rows = list(
        (
            await db.execute(
                select(DocumentFAQ)
                .where(DocumentFAQ.document_id == document.id)
                .order_by(DocumentFAQ.created_at.asc())
                .limit(2)
            )
        )
        .scalars()
        .all()
    )
    faqs = [{"question": f.question, "answer": f.answer} for f in faq_rows]

    content = (
        f"I've finished reading **{document.filename}**.\n\n"
        f"**Summary**\n{summary_row.summary.strip()}"
    )
    if faqs:
        content += "\n\n**Follow-up FAQs**"
        for i, faq in enumerate(faqs, start=1):
            content += f"\n\n{i}. **{faq['question']}**\n{faq['answer']}"

    citations: list[dict[str, Any]] = [
        {
            "kind": "ingest_brief",
            "document_id": doc_key,
            "filename": document.filename,
            "faqs": faqs,
        }
    ]

    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=content,
        citations=citations,
    )
    db.add(message)
    if session.title == "New chat":
        session.title = f"Summary · {document.filename}"[:80]
    session.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return message

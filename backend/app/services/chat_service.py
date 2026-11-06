import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.llm.base import LLMMessage
from app.llm.groq_provider import get_llm_provider
from app.models.session import ChatMessage
from app.models.user import User
from app.rag.chitchat import is_chitchat
from app.rag.citations import build_citations, filter_citations_used_in_answer
from app.rag.history import prepare_conversation_context
from app.rag.intent import classify_intent
from app.rag.prompt_builder import build_chat_messages, build_chitchat_messages
from app.rag.retriever import (
    hybrid_retrieve,
    hybrid_retrieve_per_document,
    maybe_rewrite_query,
    resolve_document_scope,
    strip_at_mentions,
)
from app.rag.types import RetrievedChunk, RetrievalResult
from app.services.document_service import get_summaries_for_docs, list_ready_documents
from app.services.session_service import SessionServiceError, get_owned_session

logger = logging.getLogger(__name__)
settings = get_settings()

CHITCHAT_FALLBACK = (
    "Hi! I'm DocChat — ask me anything about your uploaded documents, "
    "or use @filename to focus on one file."
)


def _insufficient_explanation(
    *,
    retrieval: RetrievalResult,
    question: str,
    retrieval_ran: bool,
) -> str:
    lines = [
        "I couldn't answer that from your documents with enough confidence.",
        "",
        "What happened:",
    ]
    if not retrieval_ran:
        lines.append("• Retrieval was not run for this message.")
    else:
        lines.append("• Retrieval ran (semantic + keyword search).")
        if retrieval.scoped_filenames:
            joined = ", ".join(retrieval.scoped_filenames)
            lines.append(f"• Scoped to: {joined}")
        else:
            lines.append("• Searched across all ready documents (no @ scope matched).")
        lines.append(f"• Search query used: “{retrieval.query_used or question}”")
        lines.append(f"• Candidate passages: {retrieval.candidate_count}")
        if retrieval.reason:
            lines.append(f"• Result: {retrieval.reason}")
    lines.append("")
    lines.append(
        "Try a more specific question, or @mention a ready file and ask a "
        "concrete detail (dates, names, amounts, clauses)."
    )
    return "\n".join(lines)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _default_question(scope_names: list[str]) -> str:
    if not scope_names:
        return ""
    if len(scope_names) == 1:
        return f"Summarize the key points in {scope_names[0]}"
    joined = ", ".join(scope_names)
    return f"Summarize each of these documents: {joined}"


def _summaries_as_chunks(
    rows: list[tuple[Any, Any]],
) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    for doc, summary in rows:
        if summary is None or not (summary.summary or "").strip():
            continue
        chunks.append(
            RetrievedChunk(
                chunk_id=None,
                qdrant_point_id=f"summary-{doc.id}",
                document_id=doc.id,
                filename=doc.filename,
                page_number=None,
                chunk_index=-1,
                content=summary.summary.strip(),
                score=1.0,
                source="ingest_summary",
            )
        )
    return chunks


async def stream_chat(
    db: AsyncSession,
    user: User,
    session_id: UUID,
    message: str,
    document_ids: Optional[list[UUID]] = None,
) -> AsyncIterator[str]:
    try:
        session = await get_owned_session(db, user, session_id)
    except SessionServiceError as exc:
        yield _sse("error", {"detail": exc.message})
        return

    user_msg = ChatMessage(session_id=session.id, role="user", content=message)
    db.add(user_msg)
    if session.title == "New chat":
        session.title = message.strip()[:80] or "New chat"
    session.updated_at = datetime.now(timezone.utc)
    await db.flush()

    yield _sse(
        "status",
        {"stage": "thinking", "message": "Understanding your message…"},
    )

    ctx = await prepare_conversation_context(
        db, session.id, max_turns=settings.chat_history_turns
    )
    recent_history = ctx.recent
    history_summary = ctx.summary

    # Basic chit-chat: no retrieval / embeddings / rerank
    if is_chitchat(message) and not document_ids:
        yield _sse(
            "status",
            {"stage": "generating", "message": "Replying…"},
        )
        yield _sse("sources", {"sources": []})
        async for event in _stream_llm_reply(
            db,
            session,
            messages=build_chitchat_messages(
                question=message,
                history=recent_history,
                history_summary=history_summary,
            ),
            citations=[],
            fallback_text=CHITCHAT_FALLBACK,
        ):
            yield event
        return

    scope_ids, scope_names = await resolve_document_scope(
        db, user.id, message, document_ids
    )
    stripped = strip_at_mentions(message, scope_names)
    question_was_empty = not stripped
    cleaned = stripped or _default_question(scope_names) or message.strip()

    intent = classify_intent(
        cleaned,
        scoped_count=len(scope_ids),
        question_was_empty=question_was_empty,
    )

    # Unscoped compare → use recent ready docs (capped)
    if intent == "compare" and not scope_ids:
        ready = await list_ready_documents(
            db, user, limit=settings.compare_max_docs
        )
        scope_ids = [d.id for d in ready]
        scope_names = [d.filename for d in ready]
        if question_was_empty and scope_names:
            cleaned = f"Compare these documents: {', '.join(scope_names)}"

    rewritten = maybe_rewrite_query(
        cleaned,
        recent_history,
        scoped_filenames=scope_names,
        history_summary=history_summary,
    )

    retrieval: RetrievalResult
    used_summaries = False

    if intent == "summarize" and scope_ids:
        yield _sse(
            "status",
            {"stage": "summaries", "message": "Using document summaries…"},
        )
        rows = await get_summaries_for_docs(db, user, scope_ids)
        summary_chunks = _summaries_as_chunks(rows)
        have_ids = {c.document_id for c in summary_chunks}
        missing_ids = [d for d in scope_ids if d not in have_ids]

        if summary_chunks and not missing_ids:
            used_summaries = True
            retrieval = RetrievalResult(
                chunks=summary_chunks,
                insufficient=False,
                query_used=rewritten,
                reason="Used stored ingest summaries.",
                candidate_count=len(summary_chunks),
                scoped_filenames=scope_names,
            )
        elif summary_chunks and missing_ids:
            # Mix stored summaries with retrieved chunks for docs lacking summaries
            yield _sse(
                "status",
                {
                    "stage": "searching",
                    "message": "Fetching passages for documents without summaries…",
                },
            )
            missing_set = set(missing_ids)
            missing_names = [
                n for i, n in zip(scope_ids, scope_names) if i in missing_set
            ]
            try:
                extra = await hybrid_retrieve_per_document(
                    db,
                    user_id=user.id,
                    query=rewritten,
                    document_ids=missing_ids,
                    scoped_filenames=missing_names or scope_names,
                )
            except Exception as exc:
                logger.exception("Retrieval failed")
                yield _sse("error", {"detail": f"Retrieval failed: {exc}"})
                return
            retrieval = RetrievalResult(
                chunks=summary_chunks + extra.chunks,
                insufficient=not (summary_chunks or extra.chunks),
                query_used=rewritten,
                reason="Mixed ingest summaries with retrieved passages.",
                candidate_count=len(summary_chunks) + extra.candidate_count,
                scoped_filenames=scope_names,
            )
        else:
            yield _sse(
                "status",
                {
                    "stage": "searching",
                    "message": f"Searching {', '.join(scope_names) or 'documents'}…",
                },
            )
            try:
                retrieval = await hybrid_retrieve_per_document(
                    db,
                    user_id=user.id,
                    query=rewritten,
                    document_ids=scope_ids,
                    scoped_filenames=scope_names,
                )
            except Exception as exc:
                logger.exception("Retrieval failed")
                yield _sse("error", {"detail": f"Retrieval failed: {exc}"})
                return
    elif intent == "compare":
        scope_label = ", ".join(scope_names) if scope_names else "ready documents"
        yield _sse(
            "status",
            {
                "stage": "searching",
                "message": f"Comparing across {scope_label}…",
            },
        )
        if not scope_ids:
            retrieval = RetrievalResult(
                chunks=[],
                insufficient=True,
                query_used=rewritten,
                reason="No ready documents available to compare.",
                candidate_count=0,
                scoped_filenames=[],
            )
        else:
            try:
                retrieval = await hybrid_retrieve_per_document(
                    db,
                    user_id=user.id,
                    query=rewritten,
                    document_ids=scope_ids[: settings.compare_max_docs],
                    scoped_filenames=scope_names[: settings.compare_max_docs],
                )
            except Exception as exc:
                logger.exception("Retrieval failed")
                yield _sse("error", {"detail": f"Retrieval failed: {exc}"})
                return
    else:
        scope_label = ", ".join(scope_names) if scope_names else "all ready documents"
        yield _sse(
            "status",
            {
                "stage": "searching",
                "message": f"Searching {scope_label}…",
            },
        )
        try:
            retrieval = await hybrid_retrieve(
                db,
                user_id=user.id,
                query=rewritten,
                document_ids=scope_ids or None,
                scoped_filenames=scope_names,
            )
        except Exception as exc:
            logger.exception("Retrieval failed")
            yield _sse("error", {"detail": f"Retrieval failed: {exc}"})
            return

    if not used_summaries:
        yield _sse(
            "status",
            {"stage": "ranking", "message": "Picking the most relevant passages…"},
        )

    citations = build_citations(retrieval.chunks)
    yield _sse("sources", {"sources": citations})

    if retrieval.insufficient or not retrieval.chunks:
        assistant_text = _insufficient_explanation(
            retrieval=retrieval,
            question=cleaned,
            retrieval_ran=True,
        )
        for token in _chunk_tokens(assistant_text):
            yield _sse("token", {"content": token})
        assistant = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=assistant_text,
            citations=[],
        )
        db.add(assistant)
        session.updated_at = datetime.now(timezone.utc)
        await db.flush()
        yield _sse("done", {"message_id": str(assistant.id)})
        return

    messages = build_chat_messages(
        question=cleaned or message,
        chunks=retrieval.chunks,
        history=recent_history,
        insufficient=False,
        history_summary=history_summary,
        scoped_filenames=scope_names,
        intent=intent,
    )

    yield _sse(
        "status",
        {"stage": "generating", "message": "Writing a grounded answer…"},
    )
    async for event in _stream_llm_reply(
        db,
        session,
        messages=messages,
        citations=citations,
        fallback_text=_fallback_grounded_answer(retrieval.chunks),
    ):
        yield event


async def _stream_llm_reply(
    db: AsyncSession,
    session,
    *,
    messages: list[LLMMessage],
    citations: list,
    fallback_text: str,
) -> AsyncIterator[str]:
    provider = get_llm_provider()
    if not settings.groq_api_key:
        used = filter_citations_used_in_answer(fallback_text, citations)
        for token in _chunk_tokens(fallback_text):
            yield _sse("token", {"content": token})
        yield _sse("sources", {"sources": used})
        assistant = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=fallback_text,
            citations=used or None,
        )
        db.add(assistant)
        session.updated_at = datetime.now(timezone.utc)
        await db.flush()
        yield _sse("done", {"message_id": str(assistant.id)})
        return

    collected: list[str] = []
    try:
        async for token in provider.stream(messages):
            collected.append(token)
            yield _sse("token", {"content": token})
    except Exception as exc:
        logger.exception("LLM stream failed")
        if collected:
            partial = "".join(collected)
            used = filter_citations_used_in_answer(partial, citations)
            assistant = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=partial + "\n\n[Response interrupted]",
                citations=used or None,
            )
            db.add(assistant)
            await db.flush()
            yield _sse("sources", {"sources": used})
            yield _sse(
                "error",
                {
                    "detail": f"Stream interrupted: {exc}",
                    "message_id": str(assistant.id),
                    "partial": True,
                },
            )
            return
        yield _sse("error", {"detail": f"LLM failed: {exc}"})
        return

    assistant_text = "".join(collected).strip() or fallback_text
    used = filter_citations_used_in_answer(assistant_text, citations)
    yield _sse("sources", {"sources": used})
    assistant = ChatMessage(
        id=uuid4(),
        session_id=session.id,
        role="assistant",
        content=assistant_text,
        citations=used or None,
    )
    db.add(assistant)
    session.updated_at = datetime.now(timezone.utc)
    await db.flush()
    yield _sse("done", {"message_id": str(assistant.id)})


def _chunk_tokens(text: str, size: int = 24) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _fallback_grounded_answer(chunks) -> str:
    top = chunks[0]
    page = f"page {top.page_number}" if top.page_number else "unknown page"
    snippet = top.content.strip().replace("\n", " ")
    if len(snippet) > 400:
        snippet = snippet[:400] + "…"
    return (
        f"Based on {top.filename} ({page}): {snippet}\n\n"
        f"[1]"
    )

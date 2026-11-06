"""Sliding-window chat history: keep last N turns verbatim, summarize the rest."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.locale import ENGLISH_ONLY_POLICY
from app.llm.base import LLMMessage
from app.llm.groq_provider import get_llm_provider
from app.services.session_service import load_history_pairs

logger = logging.getLogger(__name__)

# Soft cap so a long table answer does not dominate the window
_ASSISTANT_HISTORY_CHARS = 1200
_SUMMARY_MAX_CHARS = 1200


@dataclass
class ConversationContext:
    recent: list[tuple[str, str]] = field(default_factory=list)
    summary: str | None = None


def _clip_pair(role: str, content: str) -> tuple[str, str]:
    text = (content or "").strip()
    if role == "assistant" and len(text) > _ASSISTANT_HISTORY_CHARS:
        text = text[:_ASSISTANT_HISTORY_CHARS].rstrip() + "…"
    return role, text


def split_sliding_window(
    pairs: list[tuple[str, str]],
    *,
    max_turns: int,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (older, recent) where recent holds at most max_turns user/assistant pairs."""
    max_msgs = max(1, max_turns) * 2
    clipped = [_clip_pair(r, c) for r, c in pairs if r in {"user", "assistant"} and c.strip()]
    if len(clipped) <= max_msgs:
        return [], clipped
    return clipped[:-max_msgs], clipped[-max_msgs:]


def extractive_summary(older: list[tuple[str, str]]) -> str:
    """Cheap fallback when the LLM is unavailable."""
    bullets: list[str] = []
    for role, content in older:
        line = re.sub(r"\s+", " ", content).strip()
        if not line:
            continue
        if role == "user":
            bullets.append(f"- User asked: {line[:220]}")
        else:
            bullets.append(f"- Assistant: {line[:180]}")
        if len(bullets) >= 12:
            break
    text = "Earlier conversation (condensed):\n" + "\n".join(bullets)
    return text[:_SUMMARY_MAX_CHARS]


async def summarize_older_turns(older: list[tuple[str, str]]) -> str:
    if not older:
        return ""
    settings = get_settings()
    transcript = []
    for role, content in older:
        label = "User" if role == "user" else "Assistant"
        transcript.append(f"{label}: {content[:500]}")
    joined = "\n".join(transcript)
    if len(joined) > 6000:
        joined = joined[:6000] + "\n…"

    if not settings.groq_api_key:
        return extractive_summary(older)

    prompt = (
        "Summarize the earlier part of a document Q&A chat for later context.\n"
        "Keep: document names discussed, key facts/numbers already established, "
        "and open follow-ups.\n"
        "Omit: long tables, full quotes, and repeated citations.\n"
        "Write 5–10 short bullet points in English, plain text, under 180 words.\n\n"
        f"Transcript:\n{joined}"
    )
    try:
        provider = get_llm_provider()
        resp = await provider.complete(
            [
                LLMMessage(
                    role="system",
                    content=(
                        f"You compress chat history into a brief factual English summary. "
                        f"{ENGLISH_ONLY_POLICY}"
                    ),
                ),
                LLMMessage(role="user", content=prompt),
            ],
            max_tokens=320,
            temperature=0.1,
        )
        summary = (resp.content or "").strip()
        if summary:
            return ("Earlier conversation summary:\n" + summary)[:_SUMMARY_MAX_CHARS]
    except Exception:
        logger.exception("History summarization failed; using extractive fallback")
    return extractive_summary(older)


async def prepare_conversation_context(
    db: AsyncSession,
    session_id,
    *,
    max_turns: int | None = None,
) -> ConversationContext:
    """
    Load session history, keep the last `max_turns` turns verbatim,
    and summarize everything older.
    Excludes the trailing user message (the current question) from context.
    """
    settings = get_settings()
    turns = max_turns if max_turns is not None else settings.chat_history_turns
    # Fetch a large window so older turns exist for summarization
    pairs = await load_history_pairs(db, session_id, limit_turns=max(turns * 8, 40))
    if pairs and pairs[-1][0] == "user":
        pairs = pairs[:-1]

    older, recent = split_sliding_window(pairs, max_turns=turns)
    summary = await summarize_older_turns(older) if older else None
    return ConversationContext(recent=recent, summary=summary or None)

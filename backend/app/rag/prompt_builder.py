from collections import defaultdict
from typing import Literal, Optional

from app.core.locale import ENGLISH_ONLY_POLICY
from app.llm.base import LLMMessage
from app.rag.types import RetrievedChunk

ChatIntent = Literal["qa", "summarize", "compare"]

SYSTEM_PROMPT = f"""You are DocChat, a careful document assistant.
{ENGLISH_ONLY_POLICY}
Answer ONLY using the provided source excerpts for the current question.
If the sources do not contain enough information, say you cannot find that information in the uploaded documents.
Format answers in Markdown (headings, bold, bullet lists, and tables when useful).
Cite sources inline with bracketed numbers that match the excerpt ids, e.g. [1] or [3].
Only cite excerpts you actually used — do not cite every source.
Do not invent facts, page numbers, or document names.

Conversation rules:
- Recent chat turns and any earlier-conversation summary are background only.
- When the user scopes file(s), answer from those files' excerpts only.
- Do not refuse because a previous turn discussed a different file.
- Do not mix facts from a prior document into the current answer unless the current excerpts support them."""

CHITCHAT_SYSTEM_PROMPT = f"""You are DocChat, a friendly document Q&A assistant.
{ENGLISH_ONLY_POLICY}
The user is making small talk or a casual greeting — not asking about document content.
Respond briefly and warmly in English (1–3 short sentences).
Introduce yourself as DocChat if useful, and invite them to upload English documents or ask a question about their files.
Do not invent document facts. Do not pretend you retrieved sources. Do not refuse with “insufficient information”."""


def _format_chunks_flat(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        page = f"page {chunk.page_number}" if chunk.page_number else "page unknown"
        label = "ingest summary" if chunk.source == "ingest_summary" else page
        parts.append(f"[{i}] {chunk.filename} ({label})\n{chunk.content}")
    return "\n\n".join(parts)


def _format_chunks_grouped(chunks: list[RetrievedChunk]) -> str:
    """Group excerpts by filename while keeping global [n] citation ids."""
    by_file: dict[str, list[tuple[int, RetrievedChunk]]] = defaultdict(list)
    for i, chunk in enumerate(chunks, start=1):
        by_file[chunk.filename or "document"].append((i, chunk))

    sections: list[str] = []
    for filename, items in by_file.items():
        blocks = [f"### {filename}"]
        for idx, chunk in items:
            page = f"page {chunk.page_number}" if chunk.page_number else "page unknown"
            label = "ingest summary" if chunk.source == "ingest_summary" else page
            blocks.append(f"[{idx}] ({label})\n{chunk.content}")
        sections.append("\n\n".join(blocks))
    return "\n\n".join(sections)


def _scope_and_task_notes(
    *,
    intent: ChatIntent,
    scoped_filenames: Optional[list[str]],
) -> str:
    names = list(scoped_filenames or [])
    if not names:
        if intent == "compare":
            return (
                "\nCompare across the source excerpts below. Use a Markdown comparison "
                "table when helpful. Cite [n] per claim. Note gaps when a file lacks info.\n"
            )
        if intent == "summarize":
            return "\nProvide a clear English summary of the source excerpts below.\n"
        return ""

    joined = ", ".join(names)
    if len(names) == 1:
        base = f"\nThe user scoped this question to: {joined}.\n"
        if intent == "summarize":
            return base + "Summarize that document using the excerpts/summary below.\n"
        if intent == "compare":
            return base + "Only one file is in scope; summarize it rather than comparing.\n"
        return base + "Answer that document only using the excerpts below.\n"

    base = f"\nThe user scoped this question to these files: {joined}.\n"
    if intent == "summarize":
        return (
            base
            + "Provide a short summary section for each file (use the filename as a heading).\n"
        )
    if intent == "compare":
        return (
            base
            + "Compare the scoped files. Prefer a Markdown table with one column/section "
            "per file. Cite [n] for each factual claim. If a file lacks information on a "
            "topic, say so explicitly — do not invent cross-file facts.\n"
        )
    return (
        base
        + "Answer using excerpts from the scoped files. Do not invent facts that are not "
        "supported by those excerpts.\n"
    )


def _task_instruction(intent: ChatIntent) -> str:
    if intent == "summarize":
        return (
            "Provide a grounded Markdown summary in English. Cite only the excerpts "
            "you used, with [n] matching the excerpt numbers above."
        )
    if intent == "compare":
        return (
            "Provide a grounded Markdown comparison in English (table preferred). "
            "Cite only the excerpts you used, with [n] matching the excerpt numbers above."
        )
    return (
        "Provide a grounded Markdown answer in English. Cite only the excerpts "
        "you used, with [n] matching the excerpt numbers above."
    )


def build_chat_messages(
    *,
    question: str,
    chunks: list[RetrievedChunk],
    history: list[tuple[str, str]],
    insufficient: bool,
    history_summary: Optional[str] = None,
    scoped_filenames: Optional[list[str]] = None,
    intent: ChatIntent = "qa",
) -> list[LLMMessage]:
    messages: list[LLMMessage] = [LLMMessage(role="system", content=SYSTEM_PROMPT)]

    if history_summary and history_summary.strip():
        messages.append(
            LLMMessage(
                role="system",
                content=(
                    "Earlier turns were compressed into this summary "
                    f"(recent turns follow):\n{history_summary.strip()}"
                ),
            )
        )

    for role, content in history:
        if role in {"user", "assistant"} and content.strip():
            messages.append(LLMMessage(role=role, content=content))

    if insufficient or not chunks:
        context = "No sufficiently relevant document excerpts were retrieved."
    elif intent in {"summarize", "compare"}:
        context = _format_chunks_grouped(chunks)
    else:
        context = _format_chunks_flat(chunks)

    scope_note = _scope_and_task_notes(intent=intent, scoped_filenames=scoped_filenames)

    user_content = (
        f"{scope_note}"
        f"Source excerpts:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"{_task_instruction(intent)}"
    )
    messages.append(LLMMessage(role="user", content=user_content))
    return messages


def build_chitchat_messages(
    *,
    question: str,
    history: list[tuple[str, str]],
    history_summary: Optional[str] = None,
) -> list[LLMMessage]:
    messages: list[LLMMessage] = [
        LLMMessage(role="system", content=CHITCHAT_SYSTEM_PROMPT)
    ]
    if history_summary and history_summary.strip():
        messages.append(
            LLMMessage(
                role="system",
                content=f"Earlier conversation summary:\n{history_summary.strip()}",
            )
        )
    for role, content in history[-4:]:
        if role in {"user", "assistant"} and content.strip():
            messages.append(LLMMessage(role=role, content=content))
    messages.append(LLMMessage(role="user", content=question))
    return messages

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Optional

from app.core.config import get_settings
from app.core.locale import ENGLISH_ONLY_POLICY
from app.ingestion.chunker import count_tokens
from app.llm.base import LLMMessage
from app.llm.groq_provider import get_llm_provider

logger = logging.getLogger(__name__)

# Cap map-reduce fan-out so a 40k-token PDF does not spawn dozens of LLM calls
_MAX_MAP_SECTIONS = 6

ProgressCb = Optional[Callable[[str], Awaitable[None]]]


async def hierarchical_summarize(
    full_text: str,
    *,
    on_progress: ProgressCb = None,
) -> str:
    settings = get_settings()
    budget = settings.llm_input_budget
    text = full_text.strip()
    if not text:
        return "No extractable text was found in this document."

    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY unset; using extractive summary fallback")
        return _extractive_summary(text)

    tokens = count_tokens(text)
    if tokens <= budget:
        logger.info("Summarizing document in one pass (%s tokens)", tokens)
        if on_progress:
            await on_progress("Summarizing document (1 pass)…")
        return await _summarize_once(text)

    # Prefer fewer, larger sections over many tiny LLM calls
    per_section = max(budget // 2, (tokens // _MAX_MAP_SECTIONS) + 64)
    per_section = min(per_section, budget)
    sections = _split_to_budget(text, per_section)
    if len(sections) > _MAX_MAP_SECTIONS:
        sections = _coalesce_to_n(sections, _MAX_MAP_SECTIONS)

    logger.info(
        "Hierarchical summarize: %s tokens → %s sections (section_budget=%s)",
        tokens,
        len(sections),
        per_section,
    )

    partials: list[str] = []
    for idx, section in enumerate(sections, start=1):
        msg = f"Summarizing section {idx}/{len(sections)}…"
        logger.info(msg)
        if on_progress:
            await on_progress(msg)
        partials.append(await _summarize_once(section, style="section"))

    merged = "\n\n".join(partials)
    if on_progress:
        await on_progress("Merging section summaries…")
    if count_tokens(merged) > budget:
        # Second reduce pass if needed (rare with 6 sections)
        return await _summarize_once(
            _extractive_summary(merged, max_chars=budget * 3),
            style="final",
        )
    return await _summarize_once(merged, style="final")


async def generate_faqs(summary: str, count: Optional[int] = None) -> list[dict[str, str]]:
    settings = get_settings()
    n = count or settings.faqs_per_document
    if not settings.groq_api_key:
        return _fallback_faqs(summary, n)
    provider = get_llm_provider()
    prompt = (
        f"Based only on the document summary below, generate exactly {n} FAQs in English. "
        "Return strict JSON: {\"faqs\":[{\"question\":\"...\",\"answer\":\"...\"}]}. "
        "Do not invent facts not present in the summary.\n\n"
        f"SUMMARY:\n{summary}"
    )
    resp = await provider.complete(
        [
            LLMMessage(
                role="system",
                content=f"You extract FAQs from document summaries. {ENGLISH_ONLY_POLICY}",
            ),
            LLMMessage(role="user", content=prompt),
        ],
        max_tokens=800,
        temperature=0.2,
    )
    faqs = _parse_faqs(resp.content, n)
    return faqs


def _coalesce_to_n(sections: list[str], n: int) -> list[str]:
    if len(sections) <= n:
        return sections
    out: list[str] = []
    bucket = max(1, (len(sections) + n - 1) // n)
    for i in range(0, len(sections), bucket):
        out.append("\n\n".join(sections[i : i + bucket]))
    return out[:n]


def _extractive_summary(text: str, max_chars: int = 2000) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text[:max_chars]
    out: list[str] = []
    total = 0
    for p in paragraphs:
        if total + len(p) > max_chars and out:
            break
        out.append(p)
        total += len(p)
    return "\n\n".join(out)


def _fallback_faqs(summary: str, n: int) -> list[dict[str, str]]:
    snippet = summary[:280].strip() or "See the document."
    faqs = [
        {
            "question": "What is this document about?",
            "answer": snippet + ("…" if len(summary) > 280 else ""),
        },
        {
            "question": "Where can I find more detail?",
            "answer": "Refer to the full document summary and source pages for details.",
        },
    ]
    return faqs[:n]


async def _summarize_once(text: str, style: str = "final") -> str:
    provider = get_llm_provider()
    if style == "section":
        instruction = (
            f"{ENGLISH_ONLY_POLICY} "
            "Summarize this document section concisely in English, preserving key facts."
        )
    elif style == "merge":
        instruction = (
            f"{ENGLISH_ONLY_POLICY} "
            "Merge these section summaries into one coherent English summary."
        )
    else:
        instruction = (
            f"{ENGLISH_ONLY_POLICY} "
            "Write a clear, factual English summary of the document for later Q&A. "
            "Preserve important names, dates, numbers, and obligations."
        )
    resp = await provider.complete(
        [
            LLMMessage(role="system", content=instruction),
            LLMMessage(role="user", content=text),
        ],
        temperature=0.2,
    )
    return (resp.content or "").strip()


def _split_to_budget(text: str, max_tokens: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]
    sections: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}".strip() if current else para
        if count_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                sections.append(current)
            if count_tokens(para) > max_tokens:
                approx_chars = max_tokens * 4
                for i in range(0, len(para), approx_chars):
                    sections.append(para[i : i + approx_chars])
                current = ""
            else:
                current = para
    if current:
        sections.append(current)
    return sections


def _parse_faqs(raw: str, n: int) -> list[dict[str, str]]:
    text = raw.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
        items = data.get("faqs", data if isinstance(data, list) else [])
    except json.JSONDecodeError:
        logger.warning("FAQ JSON parse failed; using fallback split")
        items = []

    faqs: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question", "")).strip()
        a = str(item.get("answer", "")).strip()
        if q and a:
            faqs.append({"question": q, "answer": a})
        if len(faqs) >= n:
            break

    while len(faqs) < n:
        faqs.append(
            {
                "question": f"What is a key point from this document ({len(faqs) + 1})?",
                "answer": "See the document summary for details.",
            }
        )
    return faqs[:n]

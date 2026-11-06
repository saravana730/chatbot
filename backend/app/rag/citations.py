import re
from typing import Any

from app.rag.types import RetrievedChunk

# [1], 【1】, [ 3 ], etc.
REF_INDEX_RE = re.compile(r"[\[【]\s*(\d+)\s*[\]】]")


def build_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    """One citation per prompt excerpt, with 1-based ref matching [n] in the answer."""
    citations: list[dict] = []
    for i, chunk in enumerate(chunks, start=1):
        item = chunk.citation_dict()
        item["ref"] = i
        citations.append(item)
    return citations


def extract_cited_refs(answer: str) -> set[int]:
    return {int(m.group(1)) for m in REF_INDEX_RE.finditer(answer or "")}


def filter_citations_used_in_answer(
    answer: str, citations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep only citations the model actually referenced; dedupe by doc+page."""
    refs = extract_cited_refs(answer)
    if refs:
        used = [c for c in citations if int(c.get("ref") or 0) in refs]
    else:
        # Fallback: match filename (and page) mentioned in the answer text
        lower = (answer or "").lower()
        used = []
        for c in citations:
            name = str(c.get("filename") or "").lower()
            if not name:
                continue
            if name in lower or name.rsplit(".", 1)[0] in lower:
                used.append(c)

    if not used:
        return []

    seen: set[tuple] = set()
    deduped: list[dict[str, Any]] = []
    for c in used:
        key = (str(c.get("document_id")), c.get("page"), c.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped


def verify_citations_against_chunks(
    citations: list[dict], chunks: list[RetrievedChunk]
) -> list[dict]:
    """Keep only citations that map to retrieved chunks."""
    allowed = {
        (str(c.document_id), c.page_number, c.chunk_index) for c in chunks
    }
    verified = []
    for cite in citations:
        key = (cite.get("document_id"), cite.get("page"), cite.get("chunk_index"))
        if key in allowed:
            verified.append(cite)
    return verified or build_citations(chunks)

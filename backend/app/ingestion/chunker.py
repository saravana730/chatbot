from typing import Optional

import tiktoken

from app.core.config import get_settings
from app.ingestion.types import ContentBlock, ExtractedDocument, TextChunk


def _encoder():
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return tiktoken.get_encoding("gpt2")


def count_tokens(text: str) -> int:
    enc = _encoder()
    return len(enc.encode(text))


def chunk_document(doc: ExtractedDocument) -> list[TextChunk]:
    settings = get_settings()
    size = settings.chunk_size
    overlap = settings.chunk_overlap

    # Structure-aware: keep headings with following content; avoid splitting tables
    units = _structure_units(doc)
    chunks: list[TextChunk] = []
    buffer = ""
    buffer_page: Optional[int] = None
    chunk_index = 0

    def flush(force: bool = False) -> None:
        nonlocal buffer, buffer_page, chunk_index
        text = buffer.strip()
        if not text:
            return
        tokens = count_tokens(text)
        if tokens >= size or force:
            chunks.append(
                TextChunk(
                    content=text,
                    page_number=buffer_page,
                    chunk_index=chunk_index,
                    token_count=tokens,
                )
            )
            chunk_index += 1
            if overlap > 0 and not force:
                # Keep overlap tail
                enc = _encoder()
                ids = enc.encode(text)
                keep = ids[-overlap:] if len(ids) > overlap else ids
                buffer = enc.decode(keep)
            else:
                buffer = ""
                buffer_page = None

    for unit_text, page_number, kind in units:
        piece = unit_text.strip()
        if not piece:
            continue
        # Tables / headings: try not to split mid-unit
        candidate = f"{buffer}\n\n{piece}".strip() if buffer else piece
        if count_tokens(candidate) <= size:
            buffer = candidate
            buffer_page = buffer_page or page_number
            continue

        # Flush current buffer first
        if buffer:
            flush(force=True)

        if count_tokens(piece) <= size:
            buffer = piece
            buffer_page = page_number
            continue

        # Oversized unit (e.g. long paragraph): hard-split by tokens with overlap
        for part in _split_by_tokens(piece, size, overlap):
            chunks.append(
                TextChunk(
                    content=part,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    token_count=count_tokens(part),
                )
            )
            chunk_index += 1
        buffer = ""
        buffer_page = None

    if buffer.strip():
        flush(force=True)

    return chunks


def _structure_units(doc: ExtractedDocument) -> list[tuple[str, Optional[int], str]]:
    units: list[tuple[str, Optional[int], str]] = []
    pending_heading: Optional[ContentBlock] = None

    for page in doc.pages:
        for block in page.blocks:
            if block.kind == "heading":
                pending_heading = block
                continue
            text = block.text
            if pending_heading:
                text = f"{pending_heading.text}\n{text}"
                pending_heading = None
            units.append((text, page.page_number, block.kind))

        if pending_heading:
            units.append(
                (pending_heading.text, page.page_number, "heading")
            )
            pending_heading = None
    return units


def _split_by_tokens(text: str, size: int, overlap: int) -> list[str]:
    enc = _encoder()
    ids = enc.encode(text)
    parts: list[str] = []
    start = 0
    step = max(1, size - overlap)
    while start < len(ids):
        end = min(len(ids), start + size)
        parts.append(enc.decode(ids[start:end]))
        if end >= len(ids):
            break
        start += step
    return parts

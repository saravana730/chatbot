from app.ingestion.types import ContentBlock, ExtractedDocument, ExtractedPage


def normalize_document(doc: ExtractedDocument) -> ExtractedDocument:
    """Normalize reading order, whitespace, and page numbering."""
    normalized_pages: list[ExtractedPage] = []
    for page in doc.pages:
        blocks = sorted(page.blocks, key=lambda b: (b.reading_order, _bbox_key(b)))
        cleaned: list[ContentBlock] = []
        for i, block in enumerate(blocks):
            text = _clean_text(block.text)
            if not text:
                continue
            cleaned.append(
                ContentBlock(
                    text=text,
                    kind=block.kind,
                    page_number=page.page_number,
                    confidence=block.confidence,
                    bbox=block.bbox,
                    reading_order=i,
                )
            )
        normalized_pages.append(
            ExtractedPage(
                page_number=page.page_number,
                blocks=cleaned,
                source=page.source,
            )
        )
    return ExtractedDocument(
        pages=normalized_pages,
        filename=doc.filename,
        file_type=doc.file_type,
    )


def _clean_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _bbox_key(block: ContentBlock) -> tuple[float, float]:
    if block.bbox is None:
        return (0.0, 0.0)
    return (block.bbox.y0, block.bbox.x0)

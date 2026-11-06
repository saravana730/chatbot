import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from app.core.config import get_settings
from app.ingestion.paddle_ocr import run_paddle_ocr
from app.ingestion.tesseract import run_tesseract
from app.ingestion.types import ContentBlock, ExtractedDocument, ExtractedPage

logger = logging.getLogger(__name__)

PageProgressCb = Optional[Callable[[int, int, str], None]]


def extract_pdf(
    path: str,
    filename: str,
    *,
    on_page: PageProgressCb = None,
) -> ExtractedDocument:
    settings = get_settings()
    doc = fitz.open(path)
    pages: list[ExtractedPage] = []
    total = doc.page_count

    try:
        for i, page in enumerate(doc):
            page_number = i + 1
            if on_page:
                on_page(page_number, total, "reading")
            blocks = _native_blocks(page, page_number)
            native_text = "\n".join(b.text for b in blocks).strip()

            if len(native_text) >= settings.pdf_min_native_chars:
                pages.append(
                    ExtractedPage(page_number=page_number, blocks=blocks, source="native")
                )
                continue

            # Scanned / sparse page → OCR
            if on_page:
                on_page(page_number, total, "ocr")
            ocr_blocks = _ocr_page(page, page_number)
            if ocr_blocks:
                source = "mixed" if native_text else "ocr"
                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        blocks=ocr_blocks if not native_text else blocks + ocr_blocks,
                        source=source,
                    )
                )
            else:
                pages.append(
                    ExtractedPage(page_number=page_number, blocks=blocks, source="native")
                )
    finally:
        doc.close()

    return ExtractedDocument(pages=pages, filename=filename, file_type="pdf")


def _native_blocks(page: fitz.Page, page_number: int) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    order = 0
    try:
        data = page.get_text("dict")
    except Exception:
        text = page.get_text("text") or ""
        if text.strip():
            return [
                ContentBlock(
                    text=text.strip(),
                    kind="paragraph",
                    page_number=page_number,
                    reading_order=0,
                )
            ]
        return []

    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines = []
        for line in block.get("lines", []):
            span_text = "".join(span.get("text", "") for span in line.get("spans", []))
            if span_text.strip():
                lines.append(span_text.strip())
        text = "\n".join(lines).strip()
        if not text:
            continue
        # Heuristic heading: larger font / short line
        sizes = [
            span.get("size", 0)
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        ]
        avg_size = sum(sizes) / len(sizes) if sizes else 0
        kind = "heading" if avg_size >= 14 and len(text) < 120 else "paragraph"
        blocks.append(
            ContentBlock(
                text=text,
                kind=kind,
                page_number=page_number,
                reading_order=order,
            )
        )
        order += 1
    return blocks


def _ocr_page(page: fitz.Page, page_number: int) -> list[ContentBlock]:
    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / f"page_{page_number}.png"
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pix.save(str(img_path))
        blocks = run_paddle_ocr(str(img_path))
        if not blocks:
            blocks = run_tesseract(str(img_path))
        for b in blocks:
            b.page_number = page_number
        return blocks

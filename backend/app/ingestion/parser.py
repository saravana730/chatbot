import logging
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from app.ingestion.pdf_extractor import extract_pdf
from app.ingestion.paddle_ocr import run_paddle_ocr
from app.ingestion.tesseract import run_tesseract
from app.ingestion.types import ContentBlock, ExtractedDocument, ExtractedPage

logger = logging.getLogger(__name__)

IMAGE_TYPES = {"png", "jpg", "jpeg", "tiff", "tif"}
PageProgressCb = Optional[Callable[[int, int, str], None]]


def parse_document(
    storage_path: str,
    filename: str,
    file_type: str,
    *,
    on_page: PageProgressCb = None,
) -> ExtractedDocument:
    path = Path(storage_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {storage_path}")

    ft = file_type.lower()
    if ft == "pdf":
        return extract_pdf(str(path), filename, on_page=on_page)
    if ft in IMAGE_TYPES or ft == "jpeg":
        if on_page:
            on_page(1, 1, "ocr")
        return _parse_image(str(path), filename, ft)
    if ft == "txt":
        if on_page:
            on_page(1, 1, "reading")
        return _parse_txt(str(path), filename)
    raise ValueError(f"Unsupported file type: {file_type}")


def _parse_image(path: str, filename: str, file_type: str) -> ExtractedDocument:
    blocks = run_paddle_ocr(path)
    if not blocks:
        logger.warning("PaddleOCR empty/failed; falling back to Tesseract for %s", filename)
        blocks = run_tesseract(path)
    for b in blocks:
        b.page_number = 1
    page = ExtractedPage(page_number=1, blocks=blocks, source="ocr")
    return ExtractedDocument(pages=[page], filename=filename, file_type=file_type)


def _parse_txt(path: str, filename: str) -> ExtractedDocument:
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [raw.strip()] if raw.strip() else []
    blocks = [
        ContentBlock(text=p, kind="paragraph", page_number=1, reading_order=i)
        for i, p in enumerate(paragraphs)
    ]
    page = ExtractedPage(page_number=1, blocks=blocks, source="text")
    return ExtractedDocument(pages=[page], filename=filename, file_type="txt")

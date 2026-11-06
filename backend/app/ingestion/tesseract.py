import logging
from typing import Optional

from app.ingestion.types import ContentBlock

logger = logging.getLogger(__name__)


def run_tesseract(image_path: str) -> list[ContentBlock]:
    """Tesseract OCR fallback."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.error("pytesseract/Pillow not available")
        return []

    try:
        image = Image.open(image_path)
        # English-only to match PaddleOCR; non-English pages will be unreliable.
        data = pytesseract.image_to_data(
            image,
            lang="eng",
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        logger.exception("Tesseract failed for %s", image_path)
        return []

    blocks: list[ContentBlock] = []
    n = len(data.get("text", []))
    order = 0
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        conf_raw = data.get("conf", ["-1"])[i]
        try:
            conf = float(conf_raw) / 100.0 if float(conf_raw) >= 0 else None
        except (TypeError, ValueError):
            conf = None
        blocks.append(
            ContentBlock(
                text=text,
                kind="ocr",
                confidence=conf,
                reading_order=order,
            )
        )
        order += 1

    # Collapse into line-ish paragraphs when sparse
    if blocks:
        joined = " ".join(b.text for b in blocks)
        return [
            ContentBlock(
                text=joined,
                kind="ocr",
                confidence=_avg_conf(blocks),
                reading_order=0,
            )
        ]
    return []


def _avg_conf(blocks: list[ContentBlock]) -> Optional[float]:
    confs = [b.confidence for b in blocks if b.confidence is not None]
    if not confs:
        return None
    return sum(confs) / len(confs)

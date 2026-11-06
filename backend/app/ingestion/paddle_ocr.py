import logging
from functools import lru_cache
from typing import Optional

from app.core.config import get_settings
from app.ingestion.types import BBox, ContentBlock

logger = logging.getLogger(__name__)


@lru_cache
def _get_ocr():
    from paddleocr import PaddleOCR

    # English-only by design — Arabic/other scripts will OCR poorly.
    return PaddleOCR(use_angle_cls=True, lang="en", show_log=False)


def run_paddle_ocr(image_path: str) -> list[ContentBlock]:
    """Run PaddleOCR on an image path and return content blocks."""
    settings = get_settings()
    try:
        ocr = _get_ocr()
        result = ocr.ocr(image_path, cls=True)
    except Exception:
        logger.exception("PaddleOCR failed for %s", image_path)
        return []

    blocks: list[ContentBlock] = []
    if not result:
        return blocks

    order = 0
    for page in result:
        if not page:
            continue
        for line in page:
            try:
                box, (text, conf) = line
            except (TypeError, ValueError):
                continue
            if not text or not str(text).strip():
                continue
            confidence = float(conf) if conf is not None else None
            if confidence is not None and confidence < settings.ocr_confidence_threshold:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            blocks.append(
                ContentBlock(
                    text=str(text).strip(),
                    kind="ocr",
                    confidence=confidence,
                    bbox=BBox(min(xs), min(ys), max(xs), max(ys)),
                    reading_order=order,
                )
            )
            order += 1
    return blocks


def ocr_image_to_text(image_path: str) -> tuple[str, Optional[float], list[ContentBlock]]:
    blocks = run_paddle_ocr(image_path)
    if not blocks:
        return "", None, []
    confs = [b.confidence for b in blocks if b.confidence is not None]
    avg = sum(confs) / len(confs) if confs else None
    text = "\n".join(b.text for b in blocks)
    return text, avg, blocks

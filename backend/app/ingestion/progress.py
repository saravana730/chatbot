"""Map ingest stages + unit progress into an overall 0–100 percent."""

from __future__ import annotations

# (start_pct, end_pct) for each stage — page/chunk work fills within the band
STAGE_BANDS: dict[str, tuple[int, int]] = {
    "queued": (0, 2),
    "starting": (2, 5),
    "extracting": (5, 40),
    "ocr": (5, 40),
    "normalizing": (40, 45),
    "summarizing": (45, 72),
    "faqs": (72, 78),
    "chunking": (78, 82),
    "embedding": (82, 95),
    "indexing": (95, 99),
    "ready": (100, 100),
    "failed": (0, 0),
}


def compute_percent(
    stage: str,
    *,
    current: int | None = None,
    total: int | None = None,
) -> int:
    lo, hi = STAGE_BANDS.get(stage, (0, 100))
    if stage in {"ready"}:
        return 100
    if total and total > 0 and current is not None:
        frac = max(0.0, min(1.0, current / total))
        return int(lo + (hi - lo) * frac)
    return lo

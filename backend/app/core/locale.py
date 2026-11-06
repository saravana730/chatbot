"""DocChat product language policy: English only."""

APP_LANGUAGE = "en"

ENGLISH_ONLY_POLICY = (
    "DocChat is English-only. Always reply in clear English. "
    "Documents are expected to be English (or English OCR). "
    "If extracted text looks like non-English script or OCR gibberish, "
    "say that English text could not be extracted reliably and only use "
    "readable English fragments (names, IDs, dates, amounts)."
)

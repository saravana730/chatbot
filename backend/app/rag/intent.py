"""Lightweight chat intent classification for retrieval routing."""

from __future__ import annotations

import re
from typing import Literal

ChatIntent = Literal["qa", "summarize", "compare"]

_COMPARE_RE = re.compile(
    r"\b("
    r"compare|comparison|versus|vs\.?|difference|differences|"
    r"differ|contrast|which (policy|one|document|file)|"
    r"side[- ]by[- ]side|pros and cons"
    r")\b",
    re.IGNORECASE,
)

_SUMMARIZE_RE = re.compile(
    r"\b("
    r"summarize|summarise|summary|overview|outline|"
    r"key points?|main points?|tl;?dr|brief(ly)?|"
    r"what (is|are) (this|these|the) (doc|document|file|policy|policies)"
    r")\b",
    re.IGNORECASE,
)


def classify_intent(
    question: str,
    *,
    scoped_count: int = 0,
    question_was_empty: bool = False,
) -> ChatIntent:
    """
    Classify user intent for retrieval routing.

    - Empty text with one or more attached files → summarize
    - Compare keywords → compare
    - Summarize keywords → summarize
    - Otherwise → qa
    """
    text = (question or "").strip()
    if question_was_empty and scoped_count >= 1:
        return "summarize"
    if not text:
        return "summarize" if scoped_count >= 1 else "qa"
    if _COMPARE_RE.search(text):
        return "compare"
    if _SUMMARIZE_RE.search(text):
        return "summarize"
    return "qa"

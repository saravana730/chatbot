"""Detect basic conversational messages that should skip document retrieval."""

from __future__ import annotations

import re

# Short social / meta prompts that are not document questions
_CHITCHAT_EXACT = {
    "hi",
    "hii",
    "hello",
    "hey",
    "hey there",
    "hi there",
    "hello there",
    "good morning",
    "good afternoon",
    "good evening",
    "howdy",
    "yo",
    "sup",
    "what's up",
    "whats up",
    "how are you",
    "how r you",
    "how are you?",
    "thanks",
    "thank you",
    "thx",
    "ty",
    "ok",
    "okay",
    "cool",
    "great",
    "nice",
    "bye",
    "goodbye",
    "see you",
    "who are you",
    "what are you",
    "what can you do",
    "help",
}

_CHITCHAT_PREFIXES = (
    "hi ",
    "hello ",
    "hey ",
    "good morning",
    "good afternoon",
    "good evening",
    "thanks ",
    "thank you",
    "who are you",
    "what can you do",
    "how are you",
)

# If @document is present, always treat as a doc question
_AT_REF = re.compile(r"@\S+")


def is_chitchat(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _AT_REF.search(text):
        return False

    cleaned = re.sub(r"[!?.,]+$", "", text.lower()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    if cleaned in _CHITCHAT_EXACT:
        return True

    # Very short greetings / thanks (≤ 4 words, no question about docs)
    words = cleaned.split()
    if len(words) <= 4 and any(cleaned.startswith(p) for p in _CHITCHAT_PREFIXES):
        return True

    return False

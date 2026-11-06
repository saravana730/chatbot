"""OpenRouter remote embeddings (no local sentence-transformers load)."""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _openrouter_payload(texts: list[str], model: str) -> dict[str, Any]:
    """Multimodal-compatible text inputs for Nemotron Embed VL."""
    return {
        "model": model,
        "encoding_format": "float",
        "input": [
            {"content": [{"type": "text", "text": t}]}
            for t in texts
        ],
    }


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set; required for remote embeddings"
        )

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://docchat.local",
        "X-Title": "DocChat",
    }
    url = f"{settings.openrouter_base_url.rstrip('/')}/embeddings"
    batch_size = max(1, settings.embedding_batch_size)
    out: list[list[float]] = []

    with httpx.Client(timeout=120.0) as client:
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # Prefer simple string batch (OpenAI-compatible); fall back to VL content shape
            for payload in (
                {
                    "model": settings.embedding_model,
                    "input": batch,
                    "encoding_format": "float",
                },
                _openrouter_payload(batch, settings.embedding_model),
            ):
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    break
                logger.warning(
                    "OpenRouter embeddings HTTP %s: %s",
                    resp.status_code,
                    resp.text[:400],
                )
            else:
                resp.raise_for_status()

            data = resp.json()
            items = data.get("data") or []
            items = sorted(items, key=lambda x: x.get("index", 0))
            if len(items) != len(batch):
                raise RuntimeError(
                    f"OpenRouter returned {len(items)} embeddings for {len(batch)} inputs"
                )
            for item in items:
                vec = item.get("embedding")
                if not vec:
                    raise RuntimeError("OpenRouter embedding missing vector")
                if settings.embedding_dim and len(vec) != settings.embedding_dim:
                    logger.warning(
                        "Embedding dim %s != configured EMBEDDING_DIM=%s",
                        len(vec),
                        settings.embedding_dim,
                    )
                out.append(_l2_normalize([float(x) for x in vec]))

    return out

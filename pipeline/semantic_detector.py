"""
Semantic career page change detection.

Instead of full HTML hashing, tracks SEMANTIC changes using embeddings.
Compares old page embeddings vs new page embeddings via cosine similarity.
Only triggers job scans when meaning actually changes, not just layout/CSS.

Architecture:
    Old page text → embedding A
    New page text → embedding B
    cosine_similarity(A, B) < threshold → meaningful change detected
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import numpy as np
from html.parser import HTMLParser

from database.redis_client import get_cache, set_cache

logger = logging.getLogger(__name__)

# Lazy-loaded model
_model = None
_EMBEDDING_DIM = 384
_SIMILARITY_THRESHOLD = 0.85  # Below this = meaningful semantic change


def _get_model():
    """Lazy-load sentence transformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded embedding model for semantic detection.")
    return _model


# ── HTML → Clean Text ─────────────────────────────────────────


class _TextExtractor(HTMLParser):
    """Extract visible text from HTML, stripping tags, scripts, and styles."""

    def __init__(self) -> None:
        super().__init__()
        self.result: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            text = data.strip()
            if text:
                self.result.append(text)


def extract_text(html: str) -> str:
    """Extract visible text content from HTML."""
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.result)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Embedding Helpers ─────────────────────────────────────────


def compute_page_embedding(text: str) -> list[float]:
    """Compute normalized embedding for page text."""
    model = _get_model()
    # If text is very long, chunk it and average embeddings
    max_chars = 5000
    if len(text) > max_chars:
        chunks = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
        embeddings = model.encode(chunks, normalize_embeddings=True)
        avg = np.mean(embeddings, axis=0)
        avg = avg / (np.linalg.norm(avg) + 1e-9)
        return avg.tolist()
    else:
        return model.encode(text, normalize_embeddings=True).tolist()


def cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    a_np = np.array(a)
    b_np = np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np) + 1e-9))


# ── Redis Cache for Page Embeddings ───────────────────────────

_EMBEDDING_CACHE_PREFIX = "page_emb:"
_EMBEDDING_TTL = 86400 * 7  # 7 days


async def _get_cached_embedding(company_id: int) -> list[float] | None:
    """Retrieve cached page embedding from Redis."""
    raw = await get_cache(f"{_EMBEDDING_CACHE_PREFIX}{company_id}")
    if raw:
        return json.loads(raw)
    return None


async def _set_cached_embedding(company_id: int, embedding: list[float]) -> None:
    """Store page embedding in Redis."""
    await set_cache(
        f"{_EMBEDDING_CACHE_PREFIX}{company_id}",
        json.dumps(embedding),
        ttl=_EMBEDDING_TTL,
    )


# ── Main Detection Function ──────────────────────────────────


async def detect_semantic_change(
    company_id: int,
    new_html: str,
    threshold: float = _SIMILARITY_THRESHOLD,
) -> dict[str, Any]:
    """
    Detect if a career page has changed semantically.

    Steps:
        1. Extract text from HTML
        2. Compute embedding
        3. Compare to cached embedding
        4. Return analysis

    Returns:
        {
            "changed": bool,
            "similarity": float,
            "is_first_check": bool,
            "text_length": int,
        }
    """
    # 1. Extract text
    page_text = extract_text(new_html)
    if not page_text or len(page_text) < 50:
        return {
            "changed": False,
            "similarity": 1.0,
            "is_first_check": False,
            "text_length": len(page_text),
            "reason": "too_short",
        }

    # 2. Compute new embedding
    new_embedding = compute_page_embedding(page_text)

    # 3. Get cached embedding
    old_embedding = await _get_cached_embedding(company_id)

    if old_embedding is None:
        # First time — store and return
        await _set_cached_embedding(company_id, new_embedding)
        return {
            "changed": False,
            "similarity": 1.0,
            "is_first_check": True,
            "text_length": len(page_text),
        }

    # 4. Compare
    similarity = cosine_sim(old_embedding, new_embedding)
    changed = similarity < threshold

    if changed:
        logger.info(
            "Semantic change detected for company_id=%d (sim=%.4f < threshold=%.4f)",
            company_id,
            similarity,
            threshold,
        )
        # Update cached embedding
        await _set_cached_embedding(company_id, new_embedding)

    return {
        "changed": changed,
        "similarity": round(similarity, 4),
        "is_first_check": False,
        "text_length": len(page_text),
    }

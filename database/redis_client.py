"""Async Redis client with caching and signal deduplication helpers."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)

# ── Connection Pool ───────────────────────────────────────────

_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return a shared async Redis connection."""
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
        )
    return _pool


async def close_redis() -> None:
    """Gracefully close the Redis connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ── Generic Cache Helpers ─────────────────────────────────────


async def get_cache(key: str) -> str | None:
    """Return cached value or None."""
    r = await get_redis()
    return await r.get(key)


async def set_cache(key: str, value: str, ttl: int = 3600) -> None:
    """Set a cache key with TTL (seconds)."""
    r = await get_redis()
    await r.set(key, value, ex=ttl)


# ── Career Page Hash ─────────────────────────────────────────


async def get_page_hash(company_id: int) -> str | None:
    """Get the stored HTML hash for a company's career page."""
    return await get_cache(f"page_hash:{company_id}")


async def set_page_hash(company_id: int, html: str) -> None:
    """Store the SHA-256 hash of a career page's HTML."""
    h = hashlib.sha256(html.encode()).hexdigest()
    await set_cache(f"page_hash:{company_id}", h, ttl=86400 * 7)


def compute_hash(content: str) -> str:
    """Compute SHA-256 hex digest of arbitrary text."""
    return hashlib.sha256(content.encode()).hexdigest()


# ── Signal Deduplication ──────────────────────────────────────


async def is_duplicate_signal(company_id: int, signal_type: str, raw_data: str) -> bool:
    """
    Check if we've already processed an identical signal in the last
    SIGNAL_DEDUP_TTL seconds.  Uses a composite hash as the Redis key.
    """
    payload = f"{company_id}:{signal_type}:{raw_data}"
    sig_hash = hashlib.sha256(payload.encode()).hexdigest()
    key = f"sig_dedup:{sig_hash}"

    r = await get_redis()
    if await r.exists(key):
        return True

    # Mark as seen
    await r.set(key, "1", ex=settings.SIGNAL_DEDUP_TTL)
    return False

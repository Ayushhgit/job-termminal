"""Groq LLM client with key rotation and exponential backoff."""

from __future__ import annotations

import json
import logging
import asyncio
from typing import Any

from groq import AsyncGroq

from config import settings

logger = logging.getLogger(__name__)


# ── Key Pool with Round-Robin + Rate Limit Rotation ──────────


class _GroqKeyPool:
    """
    Manages multiple Groq API keys with automatic rotation.
    On rate limit (429), switches to the next available key.
    """

    def __init__(self) -> None:
        self._keys: list[str] = []
        self._clients: dict[str, AsyncGroq] = {}
        self._current_index: int = 0

        # Collect all non-empty keys
        for key in [
            settings.GROQ_API_KEY,
            settings.GROQ_API_KEY2,
            settings.GROQ_API_KEY3,
            settings.GROQ_API_KEY4,
        ]:
            if key:
                self._keys.append(key)
                self._clients[key] = AsyncGroq(api_key=key)

        if not self._keys:
            raise ValueError("No Groq API keys configured. Set GROQ_API_KEY in .env")

        logger.info("Groq key pool initialized with %d keys.", len(self._keys))

    @property
    def current_client(self) -> AsyncGroq:
        """Get the current active client."""
        return self._clients[self._keys[self._current_index]]

    @property
    def current_key_index(self) -> int:
        return self._current_index

    def rotate(self) -> bool:
        """
        Switch to the next key. Returns True if rotated successfully,
        False if all keys have been tried (full cycle).
        """
        next_index = (self._current_index + 1) % len(self._keys)
        if next_index == 0 and self._current_index != 0:
            # We've cycled through all keys
            logger.warning("All %d Groq keys hit rate limits.", len(self._keys))
            self._current_index = next_index
            return False
        self._current_index = next_index
        logger.info(
            "Rotated to Groq API key %d/%d",
            self._current_index + 1,
            len(self._keys),
        )
        return True

    @property
    def key_count(self) -> int:
        return len(self._keys)


_pool: _GroqKeyPool | None = None


def _get_pool() -> _GroqKeyPool:
    global _pool
    if _pool is None:
        _pool = _GroqKeyPool()
    return _pool


# ── Pre‑filter ────────────────────────────────────────────────


def should_send_to_llm(text: str) -> bool:
    """
    Quick keyword pre-filter to avoid unnecessary LLM calls.
    Only sends text to Groq if it likely contains internship signals.
    """
    text_lower = text.lower()
    return any(kw in text_lower for kw in settings.LLM_PREFILTER_KEYWORDS)


# ── Classification ────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a hiring-signal classifier. "
    "Given a text snippet, determine if it indicates an internship opportunity. "
    "Respond ONLY with valid JSON — no markdown, no explanation.\n"
    "Required JSON fields:\n"
    '  internship_detected: boolean\n'
    '  role: string (best guess at role title, or "")\n'
    '  confidence: float 0.0–1.0\n'
    '  company: string (company name mentioned, or "")\n'
)


async def classify_signal(
    text: str,
    *,
    max_retries: int = 3,
    skip_prefilter: bool = False,
) -> dict[str, Any]:
    """
    Classify a text snippet via Groq LLM with automatic key rotation.

    On rate limit (429), switches to the next API key and retries.
    """
    # Pre-filter gate
    if not skip_prefilter and not should_send_to_llm(text):
        return {
            "internship_detected": False,
            "role": "",
            "confidence": 0.0,
            "company": "",
            "skipped_by_prefilter": True,
        }

    pool = _get_pool()
    last_exc: Exception | None = None
    total_attempts = max_retries * pool.key_count  # try each key max_retries times

    for attempt in range(total_attempts):
        client = pool.current_client
        try:
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Classify if the following text indicates an internship "
                            "opportunity. Return JSON with fields internship_detected, "
                            f"role, confidence, company.\n\nText:\n{text}"
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=256,
            )

            raw = response.choices[0].message.content.strip()
            # Strip possible markdown fences
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(raw)
            result.setdefault("internship_detected", False)
            result.setdefault("role", "")
            result.setdefault("confidence", 0.0)
            result.setdefault("company", "")
            return result

        except json.JSONDecodeError as exc:
            logger.warning("Groq returned invalid JSON (attempt %d): %s", attempt + 1, exc)
            last_exc = exc
            await asyncio.sleep(2 ** (attempt % max_retries))

        except Exception as exc:  # noqa: BLE001
            exc_str = str(exc).lower()

            # Rate limit → rotate key immediately
            if "429" in exc_str or "rate" in exc_str or "limit" in exc_str:
                logger.warning(
                    "Groq rate limit on key %d/%d — rotating ...",
                    pool.current_key_index + 1,
                    pool.key_count,
                )
                pool.rotate()
                last_exc = exc
                await asyncio.sleep(1)  # brief pause before trying next key
                continue

            logger.warning("Groq API error (attempt %d): %s", attempt + 1, exc)
            last_exc = exc
            await asyncio.sleep(2 ** (attempt % max_retries))

    logger.error("Groq classification failed after %d attempts across %d keys: %s",
                 total_attempts, pool.key_count, last_exc)
    return {
        "internship_detected": False,
        "role": "",
        "confidence": 0.0,
        "company": "",
        "error": str(last_exc),
    }

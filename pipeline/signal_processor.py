"""Signal processing module — classifies raw signals via Groq LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from database.db import get_session
from database.models import Signal
from groq_client import classify_signal

logger = logging.getLogger(__name__)


async def process_signals(signals: list[Signal]) -> list[Signal]:
    """
    Send raw signals through the LLM classification pipeline.

    1. For each signal, call Groq to classify if it indicates an internship.
    2. Update the signal's `processed_result`, `confidence`, and `internship_related`.
    3. Persist updates to the database.
    4. Return the processed signals.
    """
    if not signals:
        return []

    logger.info("Processing %d signals through LLM pipeline ...", len(signals))
    processed: list[Signal] = []

    for signal in signals:
        raw_text = signal.raw_data or ""
        if not raw_text.strip():
            continue

        # ── LLM Classification (pre-filter is inside groq_client) ──
        result = await classify_signal(raw_text)

        signal.processed_result = json.dumps(result)
        signal.confidence = result.get("confidence", 0.0)
        signal.internship_related = result.get("internship_detected", False)

        processed.append(signal)

        if signal.internship_related:
            logger.info(
                "✓ Internship signal detected — company_id=%s confidence=%.2f role=%s",
                signal.company_id,
                signal.confidence,
                result.get("role", ""),
            )

    # ── Batch persist ─────────────────────────────────────────
    async with get_session() as session:
        session.add_all(processed)

    logger.info(
        "Pipeline complete — %d/%d signals classified as internship-related.",
        sum(1 for s in processed if s.internship_related),
        len(processed),
    )
    return processed

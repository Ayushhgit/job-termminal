"""
Redis Streams event pipeline for signal distribution.

Architecture:
    Agent → Redis Stream → Consumer Group → Multiple Processors

Benefits:
    - Multiple consumers can process the same signal
    - Full replay capability (signals are persisted in Redis)
    - Analytics pipeline can tap into the stream
    - Decouples signal generation from signal processing
"""

from __future__ import annotations

import logging
import asyncio
from typing import Any

import redis.asyncio as aioredis

from config import settings
from database.redis_client import get_redis

logger = logging.getLogger(__name__)

# Stream names
SIGNAL_STREAM = "signals:stream"
CONSUMER_GROUP = "signal_processors"

# ── Publishing ────────────────────────────────────────────────


async def publish_signals(signals: list[Any]) -> int:
    """
    Publish signals to the Redis Stream.

    Each signal becomes a stream entry with fields:
        company_id, signal_type, raw_data, confidence, internship_related

    Returns the count of published entries.
    """
    r = await get_redis()
    count = 0

    for signal in signals:
        entry = {
            "company_id": str(signal.company_id),
            "signal_type": signal.signal_type or "",
            "raw_data": signal.raw_data or "",
            "confidence": str(signal.confidence),
            "internship_related": str(signal.internship_related),
        }

        await r.xadd(SIGNAL_STREAM, entry, maxlen=100_000)  # Cap at 100k entries
        count += 1

    if count:
        logger.info("Published %d signals to stream '%s'", count, SIGNAL_STREAM)
    return count


# ── Consumer Group Setup ──────────────────────────────────────


async def ensure_consumer_group() -> None:
    """Create the consumer group if it doesn't already exist."""
    r = await get_redis()
    try:
        await r.xgroup_create(SIGNAL_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
        logger.info("Created consumer group '%s' on stream '%s'", CONSUMER_GROUP, SIGNAL_STREAM)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass  # Group already exists
        else:
            raise


# ── Consuming ─────────────────────────────────────────────────


async def consume_signals(
    consumer_name: str,
    handler,
    batch_size: int = 10,
    block_ms: int = 5000,
) -> None:
    """
    Consume signals from the Redis Stream using a consumer group.

    Args:
        consumer_name: Unique name for this consumer instance
        handler: Async callable(signal_data: dict) -> None
        batch_size: Number of messages to read at once
        block_ms: Block for up to this many ms waiting for new messages
    """
    r = await get_redis()
    await ensure_consumer_group()

    logger.info(
        "Consumer '%s' starting on group '%s' ...", consumer_name, CONSUMER_GROUP
    )

    while True:
        try:
            messages = await r.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=consumer_name,
                streams={SIGNAL_STREAM: ">"},
                count=batch_size,
                block=block_ms,
            )

            if not messages:
                continue

            for stream_name, entries in messages:
                for msg_id, data in entries:
                    try:
                        signal_data = {
                            "company_id": int(data.get("company_id", 0)),
                            "signal_type": data.get("signal_type", ""),
                            "raw_data": data.get("raw_data", ""),
                            "confidence": float(data.get("confidence", 0.0)),
                            "internship_related": data.get("internship_related", "False") == "True",
                        }
                        await handler(signal_data)
                        # Acknowledge processed message
                        await r.xack(SIGNAL_STREAM, CONSUMER_GROUP, msg_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "Error processing message %s: %s", msg_id, exc
                        )

        except Exception as exc:  # noqa: BLE001
            logger.error("Stream consumer error: %s", exc)
            await asyncio.sleep(1)


# ── Analytics Consumer ────────────────────────────────────────


async def analytics_handler(signal_data: dict) -> None:
    """
    Example analytics consumer that tracks signal counts.
    Can be extended for dashboards, metrics, or external webhooks.
    """
    r = await get_redis()

    # Increment signal type counter
    await r.hincrby("analytics:signal_counts", signal_data["signal_type"], 1)

    # Track high-confidence signals
    if signal_data["confidence"] > 0.7:
        await r.hincrby("analytics:high_confidence", signal_data["signal_type"], 1)

    # Track internship signals specifically
    if signal_data["internship_related"]:
        await r.hincrby("analytics:internship_signals", signal_data["signal_type"], 1)


# ── Stream Stats ──────────────────────────────────────────────


async def get_stream_stats() -> dict[str, Any]:
    """Get statistics about the event stream."""
    r = await get_redis()

    try:
        info = await r.xinfo_stream(SIGNAL_STREAM)
        stream_length = info.get("length", 0)
    except aioredis.ResponseError:
        stream_length = 0

    # Get analytics counters
    signal_counts = await r.hgetall("analytics:signal_counts") or {}
    high_conf = await r.hgetall("analytics:high_confidence") or {}
    internship = await r.hgetall("analytics:internship_signals") or {}

    return {
        "stream_length": stream_length,
        "signal_counts_by_type": signal_counts,
        "high_confidence_by_type": high_conf,
        "internship_signals_by_type": internship,
    }


# ── Replay ────────────────────────────────────────────────────


async def replay_signals(
    handler,
    start_id: str = "0",
    count: int = 1000,
) -> int:
    """
    Replay historical signals from the stream.

    Useful for:
        - Rebuilding state after a crash
        - Running new analytics on historical data
        - Debugging signal processing

    Returns the number of replayed messages.
    """
    r = await get_redis()
    messages = await r.xrange(SIGNAL_STREAM, min=start_id, count=count)
    replayed = 0

    for msg_id, data in messages:
        signal_data = {
            "company_id": int(data.get("company_id", 0)),
            "signal_type": data.get("signal_type", ""),
            "raw_data": data.get("raw_data", ""),
            "confidence": float(data.get("confidence", 0.0)),
            "internship_related": data.get("internship_related", "False") == "True",
        }
        await handler(signal_data)
        replayed += 1

    logger.info("Replayed %d signals from stream.", replayed)
    return replayed

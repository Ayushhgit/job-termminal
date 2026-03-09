"""
Arq-based distributed worker pool for processing agent tasks.

Architecture:
    Scheduler → Redis Queue (Arq) → Worker Pool (10–50 workers)

Workers process jobs like:
    crawl_company, scan_github, process_signal, deep_crawl_company
"""

from __future__ import annotations

import logging
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from config import settings
from database.db import get_session
from database.models import Company, Signal
from sqlalchemy import select

logger = logging.getLogger(__name__)


# ── Worker Functions (executed by Arq workers) ────────────────


async def crawl_company(ctx: dict, company_id: int) -> dict[str, Any]:
    """Worker task: run CareerPageAgent for a single company."""
    from agents.career_agent import CareerPageAgent
    from pipeline.signal_processor import process_signals
    from pipeline.internship_predictor import compute_probability
    from pipeline.job_discovery import deep_crawl
    from events.event_stream import publish_signals

    agent = CareerPageAgent()

    async with get_session() as session:
        company = (
            await session.execute(select(Company).where(Company.id == company_id))
        ).scalar_one_or_none()
        if not company:
            return {"status": "skipped", "reason": "company_not_found"}
        # Extract values while session is open
        company_name = company.company_name

    signals = await agent.run([company])
    if signals:
        await publish_signals(signals)  # → Redis Streams
        processed = await process_signals(signals)
        prob = await compute_probability(company_id)
        if prob >= settings.HIGH_PROBABILITY_THRESHOLD:
            await deep_crawl(company)

    return {
        "status": "done",
        "company": company_name,
        "signals_found": len(signals),
    }


async def scan_github(ctx: dict, company_id: int) -> dict[str, Any]:
    """Worker task: run GitHubHiringAgent for a single company."""
    from agents.github_agent import GitHubHiringAgent
    from pipeline.signal_processor import process_signals
    from pipeline.internship_predictor import compute_probability
    from events.event_stream import publish_signals

    agent = GitHubHiringAgent()

    async with get_session() as session:
        company = (
            await session.execute(select(Company).where(Company.id == company_id))
        ).scalar_one_or_none()
        if not company:
            return {"status": "skipped", "reason": "company_not_found"}
        company_name = company.company_name

    signals = await agent.run([company])
    if signals:
        await publish_signals(signals)
        processed = await process_signals(signals)
        await compute_probability(company_id)

    return {
        "status": "done",
        "company": company_name,
        "signals_found": len(signals),
    }


async def scan_social(ctx: dict, company_id: int) -> dict[str, Any]:
    """Worker task: run SocialSignalAgent for a single company."""
    from agents.social_agent import SocialSignalAgent
    from pipeline.signal_processor import process_signals
    from pipeline.internship_predictor import compute_probability
    from events.event_stream import publish_signals

    agent = SocialSignalAgent()

    async with get_session() as session:
        company = (
            await session.execute(select(Company).where(Company.id == company_id))
        ).scalar_one_or_none()
        if not company:
            return {"status": "skipped", "reason": "company_not_found"}
        company_name = company.company_name

    signals = await agent.run([company])
    if signals:
        await publish_signals(signals)
        processed = await process_signals(signals)
        await compute_probability(company_id)

    return {
        "status": "done",
        "company": company_name,
        "signals_found": len(signals),
    }


async def scan_funding(ctx: dict) -> dict[str, Any]:
    """Worker task: run FundingSignalAgent across all companies."""
    from agents.funding_agent import FundingSignalAgent
    from pipeline.signal_processor import process_signals
    from pipeline.internship_predictor import compute_probability
    from events.event_stream import publish_signals

    agent = FundingSignalAgent()

    async with get_session() as session:
        all_companies = (
            await session.execute(select(Company))
        ).scalars().all()

    signals = await agent.run(list(all_companies))
    if signals:
        await publish_signals(signals)
        processed = await process_signals(signals)
        for sig in processed:
            await compute_probability(sig.company_id)

    return {"status": "done", "signals_found": len(signals)}


async def process_signal_task(ctx: dict, signal_data: dict) -> dict[str, Any]:
    """Worker task: classify a single signal via LLM."""
    from pipeline.signal_processor import process_signals
    from database.models import Signal

    signal = Signal(
        company_id=signal_data["company_id"],
        signal_type=signal_data["signal_type"],
        raw_data=signal_data["raw_data"],
    )
    processed = await process_signals([signal])
    return {
        "status": "done",
        "internship_related": processed[0].internship_related if processed else False,
    }


async def deep_crawl_company(ctx: dict, company_id: int) -> dict[str, Any]:
    """Worker task: deep crawl a company's career page for job listings."""
    from pipeline.job_discovery import deep_crawl

    async with get_session() as session:
        company = (
            await session.execute(select(Company).where(Company.id == company_id))
        ).scalar_one_or_none()

    if not company:
        return {"status": "skipped", "reason": "company_not_found"}

    jobs = await deep_crawl(company)
    return {"status": "done", "jobs_found": len(jobs)}


# ── Arq Worker Settings ──────────────────────────────────────


class WorkerSettings:
    """Arq worker configuration — run with: arq workers.WorkerSettings"""
    functions = [
        crawl_company,
        scan_github,
        scan_social,
        scan_funding,
        process_signal_task,
        deep_crawl_company,
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 50  # concurrent jobs per worker
    job_timeout = 300  # 5 minutes per job
    max_tries = 3
    health_check_interval = 30


# ── Queue Helper ──────────────────────────────────────────────

_pool: ArqRedis | None = None


async def get_queue() -> ArqRedis:
    """Get or create a shared Arq Redis connection for enqueuing jobs."""
    global _pool
    if _pool is None:
        _pool = await create_pool(
            RedisSettings.from_dsn(settings.REDIS_URL)
        )
    return _pool


async def enqueue_crawl(company_id: int) -> None:
    """Enqueue a career page crawl job."""
    pool = await get_queue()
    await pool.enqueue_job("crawl_company", company_id)


async def enqueue_github(company_id: int) -> None:
    """Enqueue a GitHub scan job."""
    pool = await get_queue()
    await pool.enqueue_job("scan_github", company_id)


async def enqueue_social(company_id: int) -> None:
    """Enqueue a social scan job."""
    pool = await get_queue()
    await pool.enqueue_job("scan_social", company_id)


async def enqueue_funding() -> None:
    """Enqueue a funding RSS scan (runs across all companies)."""
    pool = await get_queue()
    await pool.enqueue_job("scan_funding")


async def enqueue_deep_crawl(company_id: int) -> None:
    """Enqueue a deep crawl job."""
    pool = await get_queue()
    await pool.enqueue_job("deep_crawl_company", company_id)

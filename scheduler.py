"""
Tiered async scheduler — upgraded to use Arq queue workers.

Architecture:
    Scheduler (this file)
        ↓ enqueue jobs
    Redis Queue (Arq)
        ↓ distributed
    Worker Pool (workers.py)
        ↓ execute
    Agent → Signal → Pipeline

The scheduler is now a lightweight job dispatcher.
Heavy processing is done by distributed Arq workers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from config import settings
from database.db import get_session
from database.models import Company, Tier
from pipeline.crawl_budget import adjust_all_budgets

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────


async def _get_company_ids_by_tier(tier: int) -> list[int]:
    """Fetch all company IDs belonging to a tier."""
    async with get_session() as session:
        q = select(Company.id).where(Company.tier == tier)
        result = await session.execute(q)
        return list(result.scalars().all())


# ── Queue-based Dispatching ──────────────────────────────────


async def _dispatch_tier_jobs(
    tier: int,
    tier_label: str,
    career_interval: int,
    github_interval: int,
    funding_interval: int,
    social_interval: int,
) -> None:
    """
    Dispatch agent jobs for a tier by enqueuing them into the Arq queue.
    Each agent type runs on its own interval within the tier.
    """
    from workers import enqueue_crawl, enqueue_github, enqueue_social, enqueue_funding

    company_ids = await _get_company_ids_by_tier(tier)
    if not company_ids:
        logger.info("No companies in %s — skipping.", tier_label)
        return

    logger.info(
        "Scheduler [%s]: %d companies | career=%dmin github=%dmin funding=%dmin social=%dmin",
        tier_label, len(company_ids),
        career_interval, github_interval, funding_interval, social_interval,
    )

    async def _career_loop() -> None:
        while True:
            ids = await _get_company_ids_by_tier(tier)
            logger.info("[%s:Career] Enqueuing %d crawl jobs ...", tier_label, len(ids))
            for cid in ids:
                await enqueue_crawl(cid)
            await asyncio.sleep(career_interval * 60)

    async def _github_loop() -> None:
        while True:
            ids = await _get_company_ids_by_tier(tier)
            logger.info("[%s:GitHub] Enqueuing %d scan jobs ...", tier_label, len(ids))
            for cid in ids:
                await enqueue_github(cid)
            await asyncio.sleep(github_interval * 60)

    async def _social_loop() -> None:
        while True:
            ids = await _get_company_ids_by_tier(tier)
            logger.info("[%s:Social] Enqueuing %d scan jobs ...", tier_label, len(ids))
            for cid in ids:
                await enqueue_social(cid)
            await asyncio.sleep(social_interval * 60)

    async def _funding_loop() -> None:
        while True:
            logger.info("[%s:Funding] Enqueuing funding scan ...", tier_label)
            await enqueue_funding()
            await asyncio.sleep(funding_interval * 60)

    await asyncio.gather(
        _career_loop(),
        _github_loop(),
        _social_loop(),
        _funding_loop(),
    )


# ── Budget Adjustment Loop ──────────────────────────────────


async def _budget_adjustment_loop() -> None:
    """Periodically adjust crawl budgets based on activity (every 6 hours)."""
    while True:
        try:
            logger.info("Running smart crawl budget adjustment ...")
            summary = await adjust_all_budgets()
            logger.info(
                "Budget adjustment: %d promoted, %d demoted, %d unchanged",
                summary["promoted"],
                summary["demoted"],
                summary["unchanged"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Budget adjustment error: %s", exc)
        await asyncio.sleep(6 * 3600)  # Every 6 hours


# ── Public Entry Point ───────────────────────────────────────


async def start_scheduler() -> None:
    """
    Launch the full tiered scheduler with queue-based dispatching.

    Tier 1 (top 5k)  → career/social every 30min, github 2hr, funding 1hr
    Tier 2 (20k)     → all agents every 3hr
    Tier 3 (25k)     → all agents every 12hr
    + Smart crawl budget adjustment every 6hr
    """
    logger.info("═══ Starting Tiered Queue Scheduler ═══")
    logger.info("Jobs will be dispatched to Arq workers via Redis queue.")
    logger.info("Start workers with: uv run arq workers.WorkerSettings")

    await asyncio.gather(
        _dispatch_tier_jobs(
            tier=Tier.TIER1,
            tier_label="Tier1",
            career_interval=settings.TIER1_INTERVAL,
            github_interval=120,
            funding_interval=60,
            social_interval=settings.TIER1_INTERVAL,
        ),
        _dispatch_tier_jobs(
            tier=Tier.TIER2,
            tier_label="Tier2",
            career_interval=settings.TIER2_INTERVAL,
            github_interval=settings.TIER2_INTERVAL,
            funding_interval=settings.TIER2_INTERVAL,
            social_interval=settings.TIER2_INTERVAL,
        ),
        _dispatch_tier_jobs(
            tier=Tier.TIER3,
            tier_label="Tier3",
            career_interval=settings.TIER3_INTERVAL,
            github_interval=settings.TIER3_INTERVAL,
            funding_interval=settings.TIER3_INTERVAL,
            social_interval=settings.TIER3_INTERVAL,
        ),
        _budget_adjustment_loop(),
    )

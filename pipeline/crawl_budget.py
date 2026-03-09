"""
Smart crawl budget — dynamically adjusts crawl frequency per company.

Instead of static tiers, the system learns which companies are
most active and allocates more crawl budget to them.

Logic:
    if company_signals_last_30_days > 5:
        increase crawl frequency (promote tier)
    if company_signals_last_30_days == 0 and last_checked > 7 days:
        decrease crawl frequency (demote tier)

Also tracks crawl efficiency: signals-per-crawl ratio.
"""

from __future__ import annotations

import datetime
import logging

from sqlalchemy import select, func as sqla_func

from database.db import get_session
from database.models import Company, Signal, Tier

logger = logging.getLogger(__name__)


# ── Thresholds ────────────────────────────────────────────────

PROMOTE_SIGNAL_COUNT = 5    # Signals in 30 days → promote tier
DEMOTE_IDLE_DAYS = 14       # No signals in 14 days → demote tier
HIGH_ACTIVITY_THRESHOLD = 10  # Very active → force Tier 1


# ── Core Budget Adjustment ────────────────────────────────────


async def adjust_crawl_budget(company_id: int) -> dict:
    """
    Dynamically adjust a company's monitoring tier based on activity.

    Returns dict with old_tier, new_tier, signal_count, action.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    thirty_days_ago = now - datetime.timedelta(days=30)

    async with get_session() as session:
        # Get company
        company = (
            await session.execute(select(Company).where(Company.id == company_id))
        ).scalar_one_or_none()

        if not company:
            return {"action": "skipped", "reason": "not_found"}

        old_tier = company.tier

        # Count signals in last 30 days
        signal_count = (
            await session.execute(
                select(sqla_func.count(Signal.id)).where(
                    Signal.company_id == company_id,
                    Signal.created_at >= thirty_days_ago,
                )
            )
        ).scalar() or 0

        # ── Decision logic ────────────────────────────────
        new_tier = old_tier
        action = "unchanged"

        if signal_count >= HIGH_ACTIVITY_THRESHOLD:
            # Very active → force Tier 1
            new_tier = Tier.TIER1
            action = "promoted_to_tier1_high_activity"

        elif signal_count >= PROMOTE_SIGNAL_COUNT:
            # Active → promote one tier
            if old_tier == Tier.TIER3:
                new_tier = Tier.TIER2
                action = "promoted_tier3_to_tier2"
            elif old_tier == Tier.TIER2:
                new_tier = Tier.TIER1
                action = "promoted_tier2_to_tier1"
            else:
                action = "already_tier1"

        elif signal_count == 0:
            # Inactive — check how long since last check
            days_since_check = None
            if company.last_checked:
                last_checked = company.last_checked
                # Ensure timezone-aware comparison
                if last_checked.tzinfo is None:
                    last_checked = last_checked.replace(tzinfo=datetime.timezone.utc)
                days_since_check = (now - last_checked).days

            if days_since_check and days_since_check >= DEMOTE_IDLE_DAYS:
                if old_tier == Tier.TIER1:
                    new_tier = Tier.TIER2
                    action = "demoted_tier1_to_tier2_idle"
                elif old_tier == Tier.TIER2:
                    new_tier = Tier.TIER3
                    action = "demoted_tier2_to_tier3_idle"
                else:
                    action = "already_tier3"

        # Apply change
        if new_tier != old_tier:
            company.tier = new_tier
            session.add(company)
            logger.info(
                "Crawl budget adjusted: %s tier %d → %d (%s, %d signals/30d)",
                company.company_name,
                old_tier,
                new_tier,
                action,
                signal_count,
            )

        return {
            "company_id": company_id,
            "company_name": company.company_name,
            "old_tier": old_tier,
            "new_tier": new_tier,
            "signal_count_30d": signal_count,
            "action": action,
        }


# ── Batch Adjustment ─────────────────────────────────────────


async def adjust_all_budgets() -> dict:
    """
    Run crawl budget adjustment for ALL companies.
    Should be called periodically (e.g., every 6 hours).

    Returns summary stats.
    """
    async with get_session() as session:
        all_ids = (
            await session.execute(select(Company.id))
        ).scalars().all()

    promoted = 0
    demoted = 0
    unchanged = 0

    for company_id in all_ids:
        result = await adjust_crawl_budget(company_id)
        action = result.get("action", "")

        if "promoted" in action:
            promoted += 1
        elif "demoted" in action:
            demoted += 1
        else:
            unchanged += 1

    summary = {
        "total_companies": len(all_ids),
        "promoted": promoted,
        "demoted": demoted,
        "unchanged": unchanged,
    }

    logger.info(
        "Budget adjustment complete: %d promoted, %d demoted, %d unchanged out of %d",
        promoted,
        demoted,
        unchanged,
        len(all_ids),
    )
    return summary


# ── Crawl Efficiency Tracking ─────────────────────────────────


async def get_crawl_efficiency() -> list[dict]:
    """
    Calculate signals-per-crawl ratio for each company.
    High ratio → company is worth crawling more often.
    Low ratio → company rarely produces signals.

    Returns sorted list (most efficient first).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    thirty_days_ago = now - datetime.timedelta(days=30)

    async with get_session() as session:
        # Get all companies with signal counts
        q = (
            select(
                Company.id,
                Company.company_name,
                Company.tier,
                sqla_func.count(Signal.id).label("signal_count"),
            )
            .outerjoin(Signal, (Signal.company_id == Company.id) & (Signal.created_at >= thirty_days_ago))
            .group_by(Company.id, Company.company_name, Company.tier)
            .order_by(sqla_func.count(Signal.id).desc())
        )
        result = await session.execute(q)
        rows = result.all()

    return [
        {
            "company_id": row[0],
            "company_name": row[1],
            "tier": row[2],
            "signal_count_30d": row[3],
            "efficiency": "high" if row[3] >= 5 else ("medium" if row[3] >= 1 else "low"),
        }
        for row in rows
    ]

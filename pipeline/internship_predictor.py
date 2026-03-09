"""Internship prediction engine — multi-factor scoring with momentum, season & history."""

from __future__ import annotations

import datetime
import logging

from sqlalchemy import select, func as sqla_func

from config import settings
from database.db import get_session
from database.models import Alert, Company, HiringHistory, Signal

logger = logging.getLogger(__name__)

# ── Seasonal weights (month → bonus) ──────────────────────────
# Summer internships recruit Dec-Feb; Fall internships Aug-Sep
_SEASONAL_BONUS: dict[int, float] = {
    1: 0.9, 2: 1.0, 3: 0.7, 4: 0.4,    # Jan-Apr: summer recruiting
    5: 0.2, 6: 0.1, 7: 0.2,             # May-Jul: low
    8: 0.8, 9: 0.9,                       # Aug-Sep: fall recruiting
    10: 0.5, 11: 0.6, 12: 0.8,           # Oct-Dec: winter/summer recruiting
}


async def compute_probability(company_id: int) -> float:
    """
    Compute a multi-factor internship probability for a company.

    Factors (configurable weights in settings):
    ─────────────────────────────────────────────
    • career_page_signal   — career page changed with internship keywords
    • github_signal        — hiring keywords found on GitHub
    • funding_signal       — recent funding event (indirect but powerful)
    • social_signal        — social media hiring mentions
    • momentum             — signal density in last 7 days
    • seasonal_weight      — time-of-year bias for internship cycles
    • history_weight       — company hired interns before

    Score formula:
        probability = w_career * career + w_github * github + w_funding * funding
                    + w_social * social + w_momentum * momentum
                    + w_seasonal * seasonal + w_history * history
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    seven_days_ago = now - datetime.timedelta(days=7)
    thirty_days_ago = now - datetime.timedelta(days=30)

    async with get_session() as session:
        # ── 1. Recent signals by type (last 30 days) ──────────
        signals_q = select(Signal).where(
            Signal.company_id == company_id,
            Signal.created_at >= thirty_days_ago,
        )
        result = await session.execute(signals_q)
        signals = result.scalars().all()

        career_score = 0.0
        github_score = 0.0
        funding_score = 0.0
        social_score = 0.0

        for sig in signals:
            conf = sig.confidence
            if sig.signal_type == "career" and sig.internship_related:
                career_score = max(career_score, conf)
            elif sig.signal_type == "github":
                github_score = max(github_score, conf)
            elif sig.signal_type == "funding":
                funding_score = max(funding_score, conf)
                # Funding boost: startups that raise money almost always hire
                funding_score = min(funding_score + 0.35, 1.0)
            elif sig.signal_type == "social" and sig.internship_related:
                social_score = max(social_score, conf)

        # ── 2. Momentum — signal count in last 7 days ─────────
        recent_count_q = select(sqla_func.count(Signal.id)).where(
            Signal.company_id == company_id,
            Signal.created_at >= seven_days_ago,
        )
        recent_count = (await session.execute(recent_count_q)).scalar() or 0
        momentum = min(recent_count / 10.0, 1.0)  # Normalize to 0–1

        # ── 3. Seasonal weight ─────────────────────────────────
        current_month = now.month
        seasonal = _SEASONAL_BONUS.get(current_month, 0.5)

        # ── 4. Historical hiring ───────────────────────────────
        history_q = select(sqla_func.count(HiringHistory.id)).where(
            HiringHistory.company_id == company_id,
        )
        history_count = (await session.execute(history_q)).scalar() or 0
        history = min(history_count * 0.25, 1.0)  # +0.25 per past hiring, cap at 1.0

        # ── 5. Weighted sum ────────────────────────────────────
        probability = (
            settings.WEIGHT_CAREER * career_score
            + settings.WEIGHT_GITHUB * github_score
            + settings.WEIGHT_FUNDING * funding_score
            + settings.WEIGHT_SOCIAL * social_score
            + settings.WEIGHT_MOMENTUM * momentum
            + settings.WEIGHT_SEASONAL * seasonal
            + settings.WEIGHT_HISTORY * history
        )
        probability = round(min(max(probability, 0.0), 1.0), 4)

        # ── 6. Update company ─────────────────────────────────
        company_q = select(Company).where(Company.id == company_id)
        company = (await session.execute(company_q)).scalar_one_or_none()

        if company:
            company.internship_probability = probability
            company.last_signal_score = probability
            company.last_checked = now
            session.add(company)

            # ── 7. Alert if above threshold ────────────────────
            if probability >= settings.HIGH_PROBABILITY_THRESHOLD:
                alert_msg = (
                    f"🚨 High probability internship opening detected for "
                    f"{company.company_name} — score: {probability:.2f} "
                    f"[career={career_score:.2f} github={github_score:.2f} "
                    f"funding={funding_score:.2f} social={social_score:.2f} "
                    f"momentum={momentum:.2f} seasonal={seasonal:.2f} "
                    f"history={history:.2f}]"
                )
                session.add(
                    Alert(
                        company_id=company_id,
                        message=alert_msg,
                        probability=probability,
                    )
                )
                logger.warning(alert_msg)

    logger.info(
        "Probability for company_id=%d: %.4f", company_id, probability
    )
    return probability

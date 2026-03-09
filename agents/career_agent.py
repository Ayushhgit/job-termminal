"""Career page monitoring agent — detects changes & scrapes for internship keywords."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agents.base_agent import BaseAgent
from database.models import Company, Signal
from database.redis_client import (
    compute_hash,
    get_page_hash,
    is_duplicate_signal,
    set_cache,
)

logger = logging.getLogger(__name__)

_INTERNSHIP_KEYWORDS = [
    "intern", "internship", "student program", "co-op",
    "summer program", "graduate program", "trainee",
    "apprentice", "early career",
]


class CareerPageAgent(BaseAgent):
    """
    1. Fetch a company's career page via httpx.
    2. Compare HTML hash against Redis cache.
    3. If changed → scan for internship keywords.
    4. Emit signals with relevant snippets.

    Uses httpx by default; Playwright fallback can be added when needed.
    """

    name = "CareerPageAgent"
    max_concurrency = 20

    async def check_company(self, company: Company) -> list[Signal]:
        if not company.careers_url:
            return []

        signals: list[Signal] = []

        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "JobIntelBot/1.0"},
            ) as client:
                resp = await client.get(company.careers_url)

                if resp.status_code != 200:
                    self.logger.debug(
                        "Non-200 (%d) for %s", resp.status_code, company.company_name
                    )
                    return []

                html = resp.text
        except httpx.HTTPError as exc:
            self.logger.debug("HTTP error for %s: %s", company.company_name, exc)
            # Could add Playwright fallback here for JS-rendered / Cloudflare pages
            return await self._playwright_fallback(company)

        # ── Change detection via hash ──────────────────────
        new_hash = compute_hash(html)
        old_hash = await get_page_hash(company.id)

        if old_hash == new_hash:
            return []  # No change

        # Store new hash
        await set_cache(f"page_hash:{company.id}", new_hash, ttl=86400 * 7)
        self.logger.info("Career page changed for %s", company.company_name)

        # ── Keyword scanning ───────────────────────────────
        html_lower = html.lower()
        found_keywords = [kw for kw in _INTERNSHIP_KEYWORDS if kw in html_lower]

        if not found_keywords:
            return []

        raw_data = (
            f"Career page change detected for {company.company_name}. "
            f"Keywords found: {', '.join(found_keywords)}"
        )

        # Dedup check
        if await is_duplicate_signal(company.id, "career", raw_data):
            return []

        signals.append(
            Signal(
                company_id=company.id,
                signal_type="career",
                raw_data=raw_data,
                confidence=min(0.3 + 0.15 * len(found_keywords), 1.0),
                internship_related=True,
            )
        )

        return signals

    # ── Playwright Fallback ───────────────────────────────────

    async def _playwright_fallback(self, company: Company) -> list[Signal]:
        """
        Fallback for JS-rendered / Cloudflare-protected career pages.
        Uses Playwright with headless Chromium.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.warning("Playwright not installed — skipping fallback for %s", company.company_name)
            return []

        signals: list[Signal] = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(company.careers_url, timeout=20000)
                await page.wait_for_load_state("networkidle")
                html = await page.content()
                await browser.close()
        except Exception as exc:
            self.logger.debug("Playwright fallback failed for %s: %s", company.company_name, exc)
            return []

        # ── Same keyword scan as above ─────────────────────
        new_hash = compute_hash(html)
        old_hash = await get_page_hash(company.id)

        if old_hash == new_hash:
            return []

        await set_cache(f"page_hash:{company.id}", new_hash, ttl=86400 * 7)

        html_lower = html.lower()
        found_keywords = [kw for kw in _INTERNSHIP_KEYWORDS if kw in html_lower]

        if not found_keywords:
            return []

        raw_data = (
            f"Career page change detected for {company.company_name} (via Playwright). "
            f"Keywords found: {', '.join(found_keywords)}"
        )

        if await is_duplicate_signal(company.id, "career", raw_data):
            return []

        signals.append(
            Signal(
                company_id=company.id,
                signal_type="career",
                raw_data=raw_data,
                confidence=min(0.3 + 0.15 * len(found_keywords), 1.0),
                internship_related=True,
            )
        )
        return signals

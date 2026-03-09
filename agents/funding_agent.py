"""Funding signal agent — monitors RSS feeds for startup funding events."""

from __future__ import annotations

import logging
from typing import Any

import feedparser
import httpx
from rapidfuzz import fuzz

from agents.base_agent import BaseAgent
from config import settings
from database.models import Company, Signal
from database.redis_client import is_duplicate_signal

logger = logging.getLogger(__name__)

# Popular startup RSS feeds
_RSS_FEEDS = [
    "https://techcrunch.com/category/startups/feed/",
    "https://news.crunchbase.com/feed/",
    "https://venturebeat.com/category/business/feed/",
]

_FUNDING_KEYWORDS = [
    "raises", "raised", "funding", "series a", "series b", "series c",
    "series d", "seed round", "pre-seed", "investment", "venture",
    "million", "billion", "closes round",
]


class FundingSignalAgent(BaseAgent):
    """
    1. Fetch RSS feeds for startup news.
    2. Detect funding announcements.
    3. Fuzzy-match company names against our database.
    4. Emit funding signals — these strongly predict hiring.
    """

    name = "FundingSignalAgent"
    max_concurrency = 5

    async def check_company(self, company: Company) -> list[Signal]:
        """Not used directly — we override `run` to batch-process feeds."""
        return []

    async def run(self, companies: list[Company]) -> list[Signal]:
        """
        Override: fetch RSS feeds once, then fuzzy-match entries against
        all companies — much more efficient than per-company calls.
        """
        self.logger.info("[%s] Fetching %d RSS feeds ...", self.name, len(_RSS_FEEDS))
        entries = await self._fetch_all_feeds()
        self.logger.info("[%s] Got %d feed entries.", self.name, len(entries))

        signals: list[Signal] = []
        company_map = {c.company_name.lower(): c for c in companies}
        company_names = list(company_map.keys())

        for entry in entries:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            text = f"{title} {summary}"
            text_lower = text.lower()

            # Check for funding keywords
            if not any(kw in text_lower for kw in _FUNDING_KEYWORDS):
                continue

            # Fuzzy match against our company list
            matched_company = self._fuzzy_match(text, company_names, company_map)
            if not matched_company:
                continue

            raw_data = f"Funding signal: {title}"

            if await is_duplicate_signal(matched_company.id, "funding", raw_data):
                continue

            signals.append(
                Signal(
                    company_id=matched_company.id,
                    signal_type="funding",
                    raw_data=raw_data,
                    confidence=0.7,
                    internship_related=False,  # Funding is indirect signal
                )
            )

        self.logger.info("[%s] Found %d funding signals.", self.name, len(signals))
        return signals

    # ── RSS Fetching ──────────────────────────────────────────

    async def _fetch_all_feeds(self) -> list[dict[str, Any]]:
        """Fetch all RSS feeds concurrently and return combined entries."""
        all_entries: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            for feed_url in _RSS_FEEDS:
                try:
                    resp = await client.get(feed_url, follow_redirects=True)
                    if resp.status_code == 200:
                        parsed = feedparser.parse(resp.text)
                        all_entries.extend(parsed.entries)
                except Exception as exc:  # noqa: BLE001
                    self.logger.debug("Feed error %s: %s", feed_url, exc)

        return all_entries

    # ── Fuzzy Matching ────────────────────────────────────────

    def _fuzzy_match(
        self,
        text: str,
        company_names: list[str],
        company_map: dict[str, Company],
    ) -> Company | None:
        """
        Find the best matching company in `text` using rapidfuzz.
        Returns the Company if score >= FUZZY_MATCH_THRESHOLD, else None.
        """
        text_lower = text.lower()
        best_score = 0
        best_name = ""

        for name in company_names:
            # Check if name appears in text (fast path)
            if name in text_lower:
                return company_map[name]

            # Fuzzy partial match
            score = fuzz.partial_ratio(name, text_lower)
            if score > best_score:
                best_score = score
                best_name = name

        if best_score >= settings.FUZZY_MATCH_THRESHOLD and best_name:
            return company_map[best_name]

        return None

"""Social signal agent — scrapes Hacker News, Reddit, and Dev.to for hiring signals."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agents.base_agent import BaseAgent
from database.models import Company, Signal
from database.redis_client import is_duplicate_signal

logger = logging.getLogger(__name__)

# Subreddits with internship and hiring discussions
_SUBREDDITS = ["internships", "csMajors", "cscareerquestions"]

# Keywords indicating internship hiring
_HIRING_KEYWORDS = [
    "intern", "internship", "co-op", "new grad", "entry level",
    "hiring", "summer program", "student", "early career",
]


class SocialSignalAgent(BaseAgent):
    """
    Real social media signal agent.

    Scrapes public hiring signals from:
    1. Hacker News (Algolia search API) — "Who is Hiring" threads
    2. Reddit (public JSON API) — r/internships, r/csMajors
    3. Dev.to (public API) — tech hiring articles

    No API keys required — all public endpoints.
    """

    name = "SocialSignalAgent"
    max_concurrency = 5  # conservative to be respectful of public APIs

    async def check_company(self, company: Company) -> list[Signal]:
        signals: list[Signal] = []

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "JobIntelBot/1.0 (research project)"},
        ) as client:
            # ── 1. Hacker News ────────────────────────────────
            hn_signals = await self._check_hackernews(client, company)
            signals.extend(hn_signals)

            # ── 2. Reddit ─────────────────────────────────────
            reddit_signals = await self._check_reddit(client, company)
            signals.extend(reddit_signals)

            # ── 3. Dev.to ─────────────────────────────────────
            devto_signals = await self._check_devto(client, company)
            signals.extend(devto_signals)

        return signals

    # ── Hacker News ───────────────────────────────────────────

    async def _check_hackernews(
        self, client: httpx.AsyncClient, company: Company
    ) -> list[Signal]:
        """Search HN Algolia API for recent hiring posts mentioning the company."""
        signals: list[Signal] = []
        query = f"{company.company_name} hiring intern"

        try:
            resp = await client.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={
                    "query": query,
                    "tags": "story,comment",
                    "numericFilters": "created_at_i>0",
                    "hitsPerPage": 5,
                },
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            for hit in data.get("hits", []):
                title = hit.get("title") or hit.get("comment_text") or ""
                # Truncate long comments
                if len(title) > 500:
                    title = title[:500] + "..."

                if not title.strip():
                    continue

                # Check if it's actually about this company + hiring
                title_lower = title.lower()
                company_lower = company.company_name.lower()
                if company_lower not in title_lower:
                    continue
                if not any(kw in title_lower for kw in _HIRING_KEYWORDS):
                    continue

                raw_data = (
                    f"HN signal for {company.company_name}: {title}"
                )

                if await is_duplicate_signal(company.id, "social", raw_data):
                    continue

                signals.append(
                    Signal(
                        company_id=company.id,
                        signal_type="social",
                        raw_data=raw_data,
                        confidence=0.6,
                        internship_related=any(
                            k in title_lower for k in ("intern", "internship", "student")
                        ),
                    )
                )

        except Exception as exc:  # noqa: BLE001
            self.logger.debug("HN search error for %s: %s", company.company_name, exc)

        return signals

    # ── Reddit ────────────────────────────────────────────────

    async def _check_reddit(
        self, client: httpx.AsyncClient, company: Company
    ) -> list[Signal]:
        """Search Reddit public JSON API for internship posts."""
        signals: list[Signal] = []

        for subreddit in _SUBREDDITS:
            try:
                resp = await client.get(
                    f"https://www.reddit.com/r/{subreddit}/search.json",
                    params={
                        "q": f"{company.company_name} intern",
                        "restrict_sr": "on",
                        "sort": "new",
                        "t": "month",
                        "limit": 5,
                    },
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                posts = data.get("data", {}).get("children", [])

                for post in posts:
                    post_data = post.get("data", {})
                    title = post_data.get("title", "")
                    selftext = post_data.get("selftext", "")[:300]
                    text = f"{title} {selftext}".strip()

                    if not text:
                        continue

                    text_lower = text.lower()
                    if company.company_name.lower() not in text_lower:
                        continue

                    raw_data = (
                        f"Reddit r/{subreddit} — {company.company_name}: {title}"
                    )

                    if await is_duplicate_signal(company.id, "social", raw_data):
                        continue

                    signals.append(
                        Signal(
                            company_id=company.id,
                            signal_type="social",
                            raw_data=raw_data,
                            confidence=0.5,
                            internship_related=any(
                                k in text_lower for k in ("intern", "internship")
                            ),
                        )
                    )

            except Exception as exc:  # noqa: BLE001
                self.logger.debug(
                    "Reddit r/%s search error for %s: %s",
                    subreddit, company.company_name, exc,
                )

        return signals

    # ── Dev.to ────────────────────────────────────────────────

    async def _check_devto(
        self, client: httpx.AsyncClient, company: Company
    ) -> list[Signal]:
        """Search Dev.to API for hiring articles."""
        signals: list[Signal] = []

        try:
            resp = await client.get(
                "https://dev.to/api/articles",
                params={
                    "tag": "hiring",
                    "per_page": 10,
                },
            )
            if resp.status_code != 200:
                return []

            articles = resp.json()
            for article in articles:
                title = article.get("title", "")
                description = article.get("description", "")
                text = f"{title} {description}"
                text_lower = text.lower()

                if company.company_name.lower() not in text_lower:
                    continue

                url = article.get("url", "")
                raw_data = (
                    f"Dev.to article for {company.company_name}: {title} — {url}"
                )

                if await is_duplicate_signal(company.id, "social", raw_data):
                    continue

                signals.append(
                    Signal(
                        company_id=company.id,
                        signal_type="social",
                        raw_data=raw_data,
                        confidence=0.55,
                        internship_related=any(
                            k in text_lower for k in ("intern", "internship")
                        ),
                    )
                )

        except Exception as exc:  # noqa: BLE001
            self.logger.debug("Dev.to error for %s: %s", company.company_name, exc)

        return signals

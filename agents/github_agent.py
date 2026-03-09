"""GitHub hiring signal agent — scans org repos for hiring keywords."""

from __future__ import annotations

import base64
import logging

import httpx

from agents.base_agent import BaseAgent
from config import settings
from database.models import Company, Signal
from database.redis_client import is_duplicate_signal

logger = logging.getLogger(__name__)

_TARGET_FILES = ["README.md", "HIRING.md", "CONTRIBUTING.md", ".github/HIRING.md"]
_HIRING_KEYWORDS = [
    "intern", "internship", "hiring", "join our team",
    "open positions", "we're hiring", "career", "apply now",
    "job opening", "looking for", "summer program",
]


class GitHubHiringAgent(BaseAgent):
    """
    1. List repos for a GitHub org.
    2. For each repo, fetch target files (README, HIRING.md, etc.).
    3. Scan content for hiring / internship keywords.
    4. Emit signals.

    Uses authenticated requests (5000 req/hr) when GITHUB_TOKEN is set.
    """

    name = "GitHubHiringAgent"
    max_concurrency = 5  # conservative to respect rate limits

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "JobIntelBot/1.0",
        }
        if settings.GITHUB_TOKEN:
            h["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
        return h

    async def check_company(self, company: Company) -> list[Signal]:
        if not company.github_org:
            return []

        signals: list[Signal] = []

        async with httpx.AsyncClient(
            timeout=15.0, headers=self._headers()
        ) as client:
            # ── 1. List repos (first page, up to 30) ──────────
            repos_url = f"https://api.github.com/orgs/{company.github_org}/repos"
            try:
                resp = await client.get(repos_url, params={"per_page": 10, "sort": "updated"})
                if resp.status_code == 403:
                    self.logger.warning("GitHub rate-limited for %s", company.github_org)
                    return []
                if resp.status_code != 200:
                    return []
                repos = resp.json()
            except httpx.HTTPError as exc:
                self.logger.debug("GitHub API error for %s: %s", company.github_org, exc)
                return []

            # ── 2. Scan target files in each repo ─────────────
            for repo in repos:
                repo_name = repo.get("full_name", "")
                for filepath in _TARGET_FILES:
                    content = await self._fetch_file(client, repo_name, filepath)
                    if not content:
                        continue

                    content_lower = content.lower()
                    found = [kw for kw in _HIRING_KEYWORDS if kw in content_lower]
                    if not found:
                        continue

                    raw_data = (
                        f"GitHub hiring signal in {repo_name}/{filepath}. "
                        f"Keywords: {', '.join(found)}"
                    )

                    if await is_duplicate_signal(company.id, "github", raw_data):
                        continue

                    signals.append(
                        Signal(
                            company_id=company.id,
                            signal_type="github",
                            raw_data=raw_data,
                            confidence=min(0.2 + 0.1 * len(found), 1.0),
                            internship_related=any(
                                k in content_lower for k in ("intern", "internship")
                            ),
                        )
                    )

        return signals

    # ── Helpers ───────────────────────────────────────────────

    async def _fetch_file(
        self, client: httpx.AsyncClient, repo_full_name: str, path: str
    ) -> str | None:
        """Fetch a file's decoded text content from a GitHub repo."""
        url = f"https://api.github.com/repos/{repo_full_name}/contents/{path}"
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("encoding") == "base64" and data.get("content"):
                return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            pass
        return None

"""Job discovery — deep crawl triggered by high-confidence hiring signals."""

from __future__ import annotations

import logging
import re

import httpx

from database.db import get_session
from database.models import Company, Job
from database.redis_client import get_cache, set_cache

logger = logging.getLogger(__name__)

_JOB_TITLE_PATTERN = re.compile(
    r"(?:intern|internship|co-op|apprentice|trainee|student|graduate)"
    r".*?(?:engineer|developer|analyst|scientist|designer|researcher|program)",
    re.IGNORECASE,
)


async def deep_crawl(company: Company) -> list[Job]:
    """
    Perform a deeper crawl of a company's career page to extract
    individual job listings. Triggered when a high-confidence hiring
    signal is detected.

    Returns list of newly discovered Job records (already persisted).
    """
    if not company.careers_url:
        return []

    cache_key = f"deep_crawl:{company.id}"
    if await get_cache(cache_key):
        logger.debug("Deep crawl cache hit for %s — skipping.", company.company_name)
        return []

    logger.info("Deep crawling career page for %s ...", company.company_name)
    jobs: list[Job] = []

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "JobIntelBot/1.0"},
        ) as client:
            resp = await client.get(company.careers_url)
            if resp.status_code != 200:
                return []
            html = resp.text

        # Simple extraction: find links that look like job postings
        # In production, use a proper HTML parser or structured API
        from html.parser import HTMLParser

        class _LinkExtractor(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.links: list[tuple[str, str]] = []  # (url, text)
                self._current_href: str | None = None
                self._current_text: list[str] = []

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag == "a":
                    href = dict(attrs).get("href", "")
                    self._current_href = href
                    self._current_text = []

            def handle_data(self, data: str) -> None:
                if self._current_href is not None:
                    self._current_text.append(data.strip())

            def handle_endtag(self, tag: str) -> None:
                if tag == "a" and self._current_href:
                    text = " ".join(self._current_text).strip()
                    if text:
                        self.links.append((self._current_href, text))
                    self._current_href = None
                    self._current_text = []

        parser = _LinkExtractor()
        parser.feed(html)

        for url, text in parser.links:
            if _JOB_TITLE_PATTERN.search(text):
                # Resolve relative URLs
                if url.startswith("/"):
                    base = company.careers_url.rstrip("/")
                    # Get base domain
                    from urllib.parse import urlparse
                    parsed = urlparse(company.careers_url)
                    url = f"{parsed.scheme}://{parsed.netloc}{url}"

                jobs.append(
                    Job(
                        company_id=company.id,
                        title=text,
                        url=url,
                        description=f"Discovered via deep crawl of {company.careers_url}",
                        source="careers_page",
                    )
                )

    except Exception as exc:  # noqa: BLE001
        logger.error("Deep crawl failed for %s: %s", company.company_name, exc)
        return []

    # Persist discovered jobs
    if jobs:
        async with get_session() as session:
            session.add_all(jobs)
        logger.info(
            "Discovered %d internship jobs for %s", len(jobs), company.company_name
        )

    # Cache to avoid re-crawling too frequently (6 hours)
    await set_cache(cache_key, "1", ttl=21600)

    return jobs

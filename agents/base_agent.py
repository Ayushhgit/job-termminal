"""Abstract base class for all signal agents."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from database.models import Company, Signal


class BaseAgent(ABC):
    """
    Base class providing shared infrastructure for signal agents:
    - batch processing
    - semaphore-based concurrency control
    - structured logging
    - error isolation per company
    """

    name: str = "BaseAgent"
    max_concurrency: int = 10  # max parallel tasks per run

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"agents.{self.name}")
        self._semaphore = asyncio.Semaphore(self.max_concurrency)

    # ── Public API ────────────────────────────────────────────

    async def run(self, companies: list[Company]) -> list[Signal]:
        """Run the agent for a batch of companies. Returns collected signals."""
        self.logger.info(
            "[%s] Starting run for %d companies ...", self.name, len(companies)
        )
        tasks = [self._safe_check(c) for c in companies]
        results = await asyncio.gather(*tasks)
        # Flatten list of lists
        signals = [s for batch in results for s in batch]
        self.logger.info(
            "[%s] Run complete — %d signals collected.", self.name, len(signals)
        )
        return signals

    # ── To Override ───────────────────────────────────────────

    @abstractmethod
    async def check_company(self, company: Company) -> list[Signal]:
        """Check a single company and return any signals found."""
        ...

    # ── Internals ─────────────────────────────────────────────

    async def _safe_check(self, company: Company) -> list[Signal]:
        """Wrap check_company with concurrency limit and error handling."""
        async with self._semaphore:
            try:
                return await self.check_company(company)
            except Exception as exc:  # noqa: BLE001
                self.logger.error(
                    "[%s] Error checking %s (id=%s): %s",
                    self.name,
                    company.company_name,
                    company.id,
                    exc,
                )
                return []

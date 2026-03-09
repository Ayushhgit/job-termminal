"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

# Load .env file from project root
_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    """Central config — values come from env vars / .env file."""

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/job_intelligence"

    # ── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Groq LLM ─────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_API_KEY2: str = ""
    GROQ_API_KEY3: str = ""
    GROQ_API_KEY4: str = ""

    # ── GitHub ────────────────────────────────────────────────
    GITHUB_TOKEN: str = ""

    # ── Tiered Monitoring Intervals (minutes) ─────────────────
    TIER1_INTERVAL: int = 30       # Top 5k companies
    TIER2_INTERVAL: int = 180      # 20k companies (3 hours)
    TIER3_INTERVAL: int = 720      # 25k companies (12 hours)

    # ── Thresholds ────────────────────────────────────────────
    HIGH_PROBABILITY_THRESHOLD: float = 0.75
    FUZZY_MATCH_THRESHOLD: int = 85
    SIGNAL_DEDUP_TTL: int = 86400  # 24 hours in seconds

    # ── Scoring Weights ───────────────────────────────────────
    WEIGHT_CAREER: float = 0.35
    WEIGHT_GITHUB: float = 0.15
    WEIGHT_FUNDING: float = 0.20
    WEIGHT_SOCIAL: float = 0.10
    WEIGHT_MOMENTUM: float = 0.10
    WEIGHT_SEASONAL: float = 0.05
    WEIGHT_HISTORY: float = 0.05

    # ── Groq Pre‑filter ──────────────────────────────────────
    LLM_PREFILTER_KEYWORDS: list[str] = [
        "intern", "internship", "student", "co-op", "coop",
        "apprentice", "trainee", "graduate program", "summer program",
    ]

    # ── Logging ───────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}


settings = Settings()

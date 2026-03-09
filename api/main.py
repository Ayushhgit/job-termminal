"""FastAPI dashboard API — exposes company, signal, job, and alert data."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import select, func as sqla_func

from config import settings
from database.db import get_session, init_db, seed_companies
from database.models import Alert, Company, Job, Signal
from database.redis_client import close_redis

logger = logging.getLogger(__name__)

# ── Configure logging ─────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s │ %(levelname)-8s │ %(name)-30s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ── Lifespan ──────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, pgvector, event streams, seed data, launch scheduler. Shutdown: cleanup."""
    # Startup
    logger.info("🚀 Initializing database ...")
    await init_db()
    await seed_companies()

    # Init pgvector store
    try:
        from pipeline.vector_search import init_vector_store
        await init_vector_store()
        logger.info("🚀 pgvector store initialized.")
    except Exception as exc:
        logger.warning("pgvector init skipped (extension may not be installed): %s", exc)

    # Init Redis Streams consumer group
    try:
        from events.event_stream import ensure_consumer_group
        await ensure_consumer_group()
        logger.info("🚀 Redis Streams consumer group ready.")
    except Exception as exc:
        logger.warning("Redis Streams init skipped: %s", exc)

    # Launch scheduler in background
    from scheduler import start_scheduler

    scheduler_task = asyncio.create_task(start_scheduler())
    logger.info("🚀 Queue scheduler launched in background.")
    logger.info("💡 Start workers with: uv run arq workers.WorkerSettings")

    yield

    # Shutdown
    scheduler_task.cancel()
    await close_redis()
    logger.info("🛑 Shutting down.")


# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="AI Job Intelligence System",
    description=(
        "Tracks up to 50,000 companies and predicts internship openings "
        "using async agents, LLM classification, multi-factor scoring, "
        "queue workers, event streaming, and vector similarity search."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Frontend Static Files ─────────────────────────────────────

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """Serve the frontend dashboard."""
    return FileResponse(str(_FRONTEND_DIR / "index.html"))


# ── Health ────────────────────────────────────────────────────


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": "job-intelligence", "version": "2.0.0"}


# ── Companies ─────────────────────────────────────────────────


@app.get("/companies", tags=["companies"])
async def list_companies(
    company_name: str | None = Query(None, description="Filter by company name (partial match)"),
    min_probability: float | None = Query(None, ge=0, le=1, description="Minimum internship probability"),
    tier: int | None = Query(None, ge=1, le=3, description="Company tier (1, 2, or 3)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List companies with optional filters and pagination."""
    async with get_session() as session:
        q = select(Company)

        if company_name:
            q = q.where(Company.company_name.ilike(f"%{company_name}%"))
        if min_probability is not None:
            q = q.where(Company.internship_probability >= min_probability)
        if tier is not None:
            q = q.where(Company.tier == tier)

        # Count
        count_q = select(sqla_func.count()).select_from(q.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        # Paginate
        q = q.order_by(Company.internship_probability.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(q)
        companies = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "companies": [
                {
                    "id": c.id,
                    "company_name": c.company_name,
                    "website": c.website,
                    "careers_url": c.careers_url,
                    "github_org": c.github_org,
                    "twitter_handle": c.twitter_handle,
                    "tier": c.tier,
                    "internship_probability": c.internship_probability,
                    "last_signal_score": c.last_signal_score,
                    "last_checked": str(c.last_checked) if c.last_checked else None,
                }
                for c in companies
            ],
        }


@app.get("/companies/high-probability", tags=["companies"])
async def high_probability_companies(
    threshold: float = Query(0.75, ge=0, le=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List companies with internship probability above threshold."""
    async with get_session() as session:
        q = (
            select(Company)
            .where(Company.internship_probability >= threshold)
            .order_by(Company.internship_probability.desc())
        )

        count_q = select(sqla_func.count()).select_from(q.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(q)
        companies = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "companies": [
                {
                    "id": c.id,
                    "company_name": c.company_name,
                    "internship_probability": c.internship_probability,
                    "careers_url": c.careers_url,
                    "last_checked": str(c.last_checked) if c.last_checked else None,
                    "tier": c.tier,
                }
                for c in companies
            ],
        }


# ── Jobs ──────────────────────────────────────────────────────


@app.get("/jobs", tags=["jobs"])
async def list_jobs(
    company_id: int | None = Query(None, description="Filter by company ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List discovered job listings."""
    async with get_session() as session:
        q = select(Job)
        if company_id is not None:
            q = q.where(Job.company_id == company_id)

        count_q = select(sqla_func.count()).select_from(q.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        q = q.order_by(Job.detected_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(q)
        jobs = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "jobs": [
                {
                    "id": j.id,
                    "company_id": j.company_id,
                    "title": j.title,
                    "url": j.url,
                    "description": j.description,
                    "source": j.source,
                    "detected_at": str(j.detected_at),
                }
                for j in jobs
            ],
        }


# ── Signals ───────────────────────────────────────────────────


@app.get("/signals", tags=["signals"])
async def list_signals(
    signal_type: str | None = Query(None, description="Filter: career | github | funding | social"),
    company_id: int | None = Query(None, description="Filter by company ID"),
    internship_only: bool = Query(False, description="Only internship-related signals"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List collected signals with optional filters."""
    async with get_session() as session:
        q = select(Signal)
        if signal_type:
            q = q.where(Signal.signal_type == signal_type)
        if company_id is not None:
            q = q.where(Signal.company_id == company_id)
        if internship_only:
            q = q.where(Signal.internship_related == True)  # noqa: E712

        count_q = select(sqla_func.count()).select_from(q.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        q = q.order_by(Signal.created_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(q)
        signals = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "signals": [
                {
                    "id": s.id,
                    "company_id": s.company_id,
                    "signal_type": s.signal_type,
                    "raw_data": s.raw_data,
                    "processed_result": s.processed_result,
                    "confidence": s.confidence,
                    "internship_related": s.internship_related,
                    "created_at": str(s.created_at),
                }
                for s in signals
            ],
        }


# ── Alerts ────────────────────────────────────────────────────


@app.get("/alerts", tags=["alerts"])
async def list_alerts(
    company_id: int | None = Query(None, description="Filter by company ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List generated alerts."""
    async with get_session() as session:
        q = select(Alert)
        if company_id is not None:
            q = q.where(Alert.company_id == company_id)

        count_q = select(sqla_func.count()).select_from(q.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        q = q.order_by(Alert.created_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(q)
        alerts = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "alerts": [
                {
                    "id": a.id,
                    "company_id": a.company_id,
                    "message": a.message,
                    "probability": a.probability,
                    "created_at": str(a.created_at),
                }
                for a in alerts
            ],
        }


# ── Stats ─────────────────────────────────────────────────────


@app.get("/stats", tags=["system"])
async def system_stats():
    """System-wide statistics including event stream metrics."""
    async with get_session() as session:
        companies_total = (
            await session.execute(select(sqla_func.count(Company.id)))
        ).scalar() or 0
        signals_total = (
            await session.execute(select(sqla_func.count(Signal.id)))
        ).scalar() or 0
        jobs_total = (
            await session.execute(select(sqla_func.count(Job.id)))
        ).scalar() or 0
        alerts_total = (
            await session.execute(select(sqla_func.count(Alert.id)))
        ).scalar() or 0
        high_prob = (
            await session.execute(
                select(sqla_func.count(Company.id)).where(
                    Company.internship_probability >= settings.HIGH_PROBABILITY_THRESHOLD
                )
            )
        ).scalar() or 0

        # Tier breakdown
        tier_counts = {}
        for tier_val in (1, 2, 3):
            cnt = (
                await session.execute(
                    select(sqla_func.count(Company.id)).where(Company.tier == tier_val)
                )
            ).scalar() or 0
            tier_counts[f"tier_{tier_val}"] = cnt

    # Event stream stats
    try:
        from events.event_stream import get_stream_stats
        stream_stats = await get_stream_stats()
    except Exception:
        stream_stats = {}

    return {
        "companies_total": companies_total,
        "signals_total": signals_total,
        "jobs_total": jobs_total,
        "alerts_total": alerts_total,
        "high_probability_companies": high_prob,
        "tier_breakdown": tier_counts,
        "event_stream": stream_stats,
    }


# ── Vector Search ─────────────────────────────────────────────


@app.get("/signals/search", tags=["vector-search"])
async def search_similar_signals(
    query: str = Query(..., description="Natural language query (e.g. 'ML internship')"),
    limit: int = Query(10, ge=1, le=100),
    min_similarity: float = Query(0.5, ge=0, le=1),
):
    """
    Find signals similar to a natural language query using vector search.
    Powered by pgvector with sentence-transformer embeddings.
    """
    try:
        from pipeline.vector_search import find_similar_signals
        results = await find_similar_signals(query, limit=limit, min_similarity=min_similarity)
        return {"query": query, "results": results, "count": len(results)}
    except Exception as exc:
        return {"query": query, "results": [], "count": 0, "error": str(exc)}


# ── Event Stream ──────────────────────────────────────────────


@app.get("/stream/stats", tags=["event-stream"])
async def stream_statistics():
    """Get Redis Streams event pipeline statistics."""
    try:
        from events.event_stream import get_stream_stats
        return await get_stream_stats()
    except Exception as exc:
        return {"error": str(exc)}


# ── Crawl Budget ──────────────────────────────────────────────


@app.post("/budget/adjust", tags=["crawl-budget"])
async def trigger_budget_adjustment():
    """Manually trigger smart crawl budget adjustment for all companies."""
    try:
        from pipeline.crawl_budget import adjust_all_budgets
        summary = await adjust_all_budgets()
        return {"status": "done", **summary}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@app.get("/budget/efficiency", tags=["crawl-budget"])
async def crawl_efficiency():
    """Get crawl efficiency (signals-per-crawl ratio) for all companies."""
    try:
        from pipeline.crawl_budget import get_crawl_efficiency
        data = await get_crawl_efficiency()
        return {"companies": data, "count": len(data)}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/budget/adjust/{company_id}", tags=["crawl-budget"])
async def adjust_single_company(company_id: int):
    """Adjust crawl budget for a single company."""
    try:
        from pipeline.crawl_budget import adjust_crawl_budget
        result = await adjust_crawl_budget(company_id)
        return result
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ── Manual Scan ───────────────────────────────────────────────


@app.post("/scan/now", tags=["scan"])
async def scan_now(
    max_companies: int = Query(20, ge=1, le=200, description="Max companies to scan"),
):
    """
    Trigger an immediate scan of companies using all 4 agents directly.
    Bypasses the Arq queue for instant results — useful for demos and testing.
    """
    from agents.career_agent import CareerPageAgent
    from agents.github_agent import GitHubHiringAgent
    from agents.funding_agent import FundingSignalAgent
    from agents.social_agent import SocialSignalAgent
    from pipeline.signal_processor import process_signals
    from pipeline.internship_predictor import compute_probability
    from pipeline.job_discovery import deep_crawl

    async with get_session() as session:
        q = select(Company).order_by(Company.tier).limit(max_companies)
        result = await session.execute(q)
        companies = list(result.scalars().all())

    if not companies:
        return {"status": "no_companies", "signals": 0}

    logger.info("Manual scan starting for %d companies ...", len(companies))
    all_signals: list[Signal] = []

    # Run all agents
    career_agent = CareerPageAgent()
    github_agent = GitHubHiringAgent()
    social_agent = SocialSignalAgent()
    funding_agent = FundingSignalAgent()

    career_signals = await career_agent.run(companies)
    github_signals = await github_agent.run(companies)
    social_signals = await social_agent.run(companies)
    funding_signals = await funding_agent.run(companies)

    all_signals = career_signals + github_signals + social_signals + funding_signals

    # Process through LLM pipeline
    processed = []
    if all_signals:
        processed = await process_signals(all_signals)

    # Compute probabilities for companies that got signals
    company_ids_with_signals = set(s.company_id for s in all_signals)
    for cid in company_ids_with_signals:
        prob = await compute_probability(cid)
        if prob >= settings.HIGH_PROBABILITY_THRESHOLD:
            # Find the company object
            comp = next((c for c in companies if c.id == cid), None)
            if comp:
                await deep_crawl(comp)

    return {
        "status": "done",
        "companies_scanned": len(companies),
        "signals_found": len(all_signals),
        "signals_by_type": {
            "career": len(career_signals),
            "github": len(github_signals),
            "social": len(social_signals),
            "funding": len(funding_signals),
        },
        "processed": len(processed),
        "internship_signals": sum(1 for s in processed if s.internship_related),
    }


@app.post("/scan/company/{company_id}", tags=["scan"])
async def scan_single_company(company_id: int):
    """Scan a single company using all agents. Returns signals immediately."""
    from agents.career_agent import CareerPageAgent
    from agents.github_agent import GitHubHiringAgent
    from agents.social_agent import SocialSignalAgent
    from pipeline.signal_processor import process_signals
    from pipeline.internship_predictor import compute_probability
    from pipeline.job_discovery import deep_crawl

    async with get_session() as session:
        company = (
            await session.execute(select(Company).where(Company.id == company_id))
        ).scalar_one_or_none()

    if not company:
        return {"status": "error", "reason": "company_not_found"}

    all_signals: list[Signal] = []

    career_signals = await CareerPageAgent().run([company])
    github_signals = await GitHubHiringAgent().run([company])
    social_signals = await SocialSignalAgent().run([company])

    all_signals = career_signals + github_signals + social_signals

    processed = []
    if all_signals:
        processed = await process_signals(all_signals)

    prob = await compute_probability(company_id)
    if prob >= settings.HIGH_PROBABILITY_THRESHOLD:
        await deep_crawl(company)

    return {
        "status": "done",
        "company": company.company_name,
        "signals_found": len(all_signals),
        "signals_by_type": {
            "career": len(career_signals),
            "github": len(github_signals),
            "social": len(social_signals),
        },
        "internship_probability": prob,
        "signals": [
            {
                "type": s.signal_type,
                "raw_data": s.raw_data,
                "confidence": s.confidence,
                "internship_related": s.internship_related,
            }
            for s in all_signals
        ],
    }

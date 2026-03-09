"""Async database engine, session factory, init helpers, and CSV import."""

from __future__ import annotations

import csv
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from database.models import Base, Company, Tier

logger = logging.getLogger(__name__)

# ── Engine & Session ──────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Schema Bootstrap ─────────────────────────────────────────


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified.")


# ── Seed Data ─────────────────────────────────────────────────

_SEED_COMPANIES = [
    # ═══════════════════════════════════════════════════════
    # TIER 1 — FAANG, Top AI/ML, Major Unicorns (35 companies)
    # ═══════════════════════════════════════════════════════
    ("Google", "https://google.com", "https://www.google.com/about/careers/applications/", "google", "Google", Tier.TIER1),
    ("Microsoft", "https://microsoft.com", "https://careers.microsoft.com/", "microsoft", "Microsoft", Tier.TIER1),
    ("Apple", "https://apple.com", "https://jobs.apple.com/", "apple", "Apple", Tier.TIER1),
    ("Meta", "https://meta.com", "https://www.metacareers.com/", "facebook", "Meta", Tier.TIER1),
    ("Amazon", "https://amazon.com", "https://www.amazon.jobs/", "amzn", "AmazonNews", Tier.TIER1),
    ("Netflix", "https://netflix.com", "https://jobs.netflix.com/", "Netflix", "netflix", Tier.TIER1),
    ("NVIDIA", "https://nvidia.com", "https://www.nvidia.com/en-us/about-nvidia/careers/", "NVIDIA", "nvidia", Tier.TIER1),
    ("Tesla", "https://tesla.com", "https://www.tesla.com/careers", "teslamotors", "Tesla", Tier.TIER1),
    ("OpenAI", "https://openai.com", "https://openai.com/careers/", "openai", "OpenAI", Tier.TIER1),
    ("Anthropic", "https://anthropic.com", "https://www.anthropic.com/careers", "anthropics", "AnthropicAI", Tier.TIER1),
    ("DeepMind", "https://deepmind.google", "https://deepmind.google/about/careers/", "google-deepmind", "GoogleDeepMind", Tier.TIER1),
    ("Stripe", "https://stripe.com", "https://stripe.com/jobs", "stripe", "stripe", Tier.TIER1),
    ("Salesforce", "https://salesforce.com", "https://careers.salesforce.com/", "salesforce", "salesforce", Tier.TIER1),
    ("Adobe", "https://adobe.com", "https://careers.adobe.com/", "adobe", "Adobe", Tier.TIER1),
    ("Intel", "https://intel.com", "https://jobs.intel.com/", "intel", "intel", Tier.TIER1),
    ("IBM", "https://ibm.com", "https://www.ibm.com/careers", "IBM", "IBM", Tier.TIER1),
    ("Oracle", "https://oracle.com", "https://www.oracle.com/careers/", "oracle", "Oracle", Tier.TIER1),
    ("Uber", "https://uber.com", "https://www.uber.com/us/en/careers/", "uber", "Uber", Tier.TIER1),
    ("Airbnb", "https://airbnb.com", "https://careers.airbnb.com/", "airbnb", "Airbnb", Tier.TIER1),
    ("Spotify", "https://spotify.com", "https://www.lifeatspotify.com/jobs", "spotify", "Spotify", Tier.TIER1),
    ("LinkedIn", "https://linkedin.com", "https://careers.linkedin.com/", "linkedin", "LinkedIn", Tier.TIER1),
    ("Twitter", "https://x.com", "https://careers.twitter.com/", "twitter", "X", Tier.TIER1),
    ("Snap", "https://snap.com", "https://snap.com/en-US/jobs", "Snapchat", "Snapchat", Tier.TIER1),
    ("Pinterest", "https://pinterest.com", "https://www.pinterestcareers.com/", "pinterest", "Pinterest", Tier.TIER1),
    ("Coinbase", "https://coinbase.com", "https://www.coinbase.com/careers", "coinbase", "coinbase", Tier.TIER1),
    ("Block", "https://block.xyz", "https://block.xyz/careers", "square", "blocks", Tier.TIER1),
    ("Qualcomm", "https://qualcomm.com", "https://www.qualcomm.com/company/careers", "qualcomm", "Qualcomm", Tier.TIER1),
    ("AMD", "https://amd.com", "https://www.amd.com/en/corporate/careers.html", "GPUOpen-LibrariesAndSDKs", "AMD", Tier.TIER1),
    ("Palantir", "https://palantir.com", "https://www.palantir.com/careers/", "palantir", "PalantirTech", Tier.TIER1),
    ("Databricks", "https://databricks.com", "https://www.databricks.com/company/careers", "databricks", "datababoricks", Tier.TIER1),
    ("ByteDance", "https://bytedance.com", "https://jobs.bytedance.com/", "nicklockwood", "BytedanceTalk", Tier.TIER1),
    ("Samsung", "https://samsung.com", "https://www.samsung.com/us/careers/", "nicklockwood", "SamsungMobile", Tier.TIER1),
    ("Cisco", "https://cisco.com", "https://jobs.cisco.com/", "cisco", "Cisco", Tier.TIER1),
    ("VMware", "https://vmware.com", "https://careers.vmware.com/", "vmware", "VMware", Tier.TIER1),
    ("SAP", "https://sap.com", "https://jobs.sap.com/", "SAP", "SAP", Tier.TIER1),
    # ═══════════════════════════════════════════════════════
    # TIER 2 — Growth-Stage Tech, Fintech, Health-Tech (40 companies)
    # ═══════════════════════════════════════════════════════
    ("Shopify", "https://shopify.com", "https://www.shopify.com/careers", "Shopify", "Shopify", Tier.TIER2),
    ("Datadog", "https://datadoghq.com", "https://careers.datadoghq.com/", "DataDog", "databorwhq", Tier.TIER2),
    ("Snowflake", "https://snowflake.com", "https://careers.snowflake.com/", "snowflakedb", "SnowflakeDB", Tier.TIER2),
    ("Cloudflare", "https://cloudflare.com", "https://www.cloudflare.com/careers/", "cloudflare", "Cloudflare", Tier.TIER2),
    ("Twilio", "https://twilio.com", "https://www.twilio.com/company/jobs", "twilio", "twilio", Tier.TIER2),
    ("Figma", "https://figma.com", "https://www.figma.com/careers/", "figma", "figma", Tier.TIER2),
    ("Canva", "https://canva.com", "https://www.canva.com/careers/", "canva", "canva", Tier.TIER2),
    ("Slack", "https://slack.com", "https://slack.com/careers", "slackapi", "SlackHQ", Tier.TIER2),
    ("Atlassian", "https://atlassian.com", "https://www.atlassian.com/company/careers", "atlassian", "Atlassian", Tier.TIER2),
    ("GitLab", "https://gitlab.com", "https://about.gitlab.com/jobs/", "gitlabhq", "gitlab", Tier.TIER2),
    ("GitHub", "https://github.com", "https://github.com/about/careers", "github", "github", Tier.TIER2),
    ("Elastic", "https://elastic.co", "https://www.elastic.co/careers/", "elastic", "elastic", Tier.TIER2),
    ("MongoDB", "https://mongodb.com", "https://www.mongodb.com/company/careers", "mongodb", "MongoDB", Tier.TIER2),
    ("Confluent", "https://confluent.io", "https://www.confluent.io/careers/", "confluentinc", "confluentinc", Tier.TIER2),
    ("HashiCorp", "https://hashicorp.com", "https://www.hashicorp.com/careers", "hashicorp", "HashiCorp", Tier.TIER2),
    ("Splunk", "https://splunk.com", "https://www.splunk.com/en_us/careers.html", "splunk", "splunk", Tier.TIER2),
    ("Palo Alto Networks", "https://paloaltonetworks.com", "https://jobs.paloaltonetworks.com/", "PaloAltoNetworks", "PaloAltoNtwks", Tier.TIER2),
    ("CrowdStrike", "https://crowdstrike.com", "https://www.crowdstrike.com/careers/", "CrowdStrike", "CrowdStrike", Tier.TIER2),
    ("Plaid", "https://plaid.com", "https://plaid.com/careers/", "plaid", "PlaidInc", Tier.TIER2),
    ("Rippling", "https://rippling.com", "https://www.rippling.com/careers", "Rippling", "Rippling", Tier.TIER2),
    ("Scale AI", "https://scale.com", "https://scale.com/careers", "scaleapi", "scale_AI", Tier.TIER2),
    ("Anduril", "https://anduril.com", "https://www.anduril.com/careers/", "anduril", "anaborduriltech", Tier.TIER2),
    ("Ramp", "https://ramp.com", "https://ramp.com/careers", "RampHQ", "tryramp", Tier.TIER2),
    ("Brex", "https://brex.com", "https://www.brex.com/careers", "brexhq", "braborexhq", Tier.TIER2),
    ("Robinhood", "https://robinhood.com", "https://careers.robinhood.com/", "robinhoodapi", "RobinhoodApp", Tier.TIER2),
    ("DoorDash", "https://doordash.com", "https://careers.doordash.com/", "doordash", "DoorDash", Tier.TIER2),
    ("Instacart", "https://instacart.com", "https://instacart.careers/", "instacart", "Instacart", Tier.TIER2),
    ("Lyft", "https://lyft.com", "https://www.lyft.com/careers", "lyft", "lyft", Tier.TIER2),
    ("Reddit", "https://reddit.com", "https://www.redditinc.com/careers", "reddit", "Reddit", Tier.TIER2),
    ("Discord", "https://discord.com", "https://discord.com/careers", "discord", "discord", Tier.TIER2),
    ("Notion", "https://notion.so", "https://www.notion.so/careers", "makenotion", "NotionHQ", Tier.TIER2),
    ("Airtable", "https://airtable.com", "https://airtable.com/careers", "Airtable", "airtable", Tier.TIER2),
    ("Grammarly", "https://grammarly.com", "https://www.grammarly.com/careers", "grammarly", "Grammarly", Tier.TIER2),
    ("HubSpot", "https://hubspot.com", "https://www.hubspot.com/careers", "HubSpot", "HubSpot", Tier.TIER2),
    ("Okta", "https://okta.com", "https://www.okta.com/company/careers/", "okta", "okta", Tier.TIER2),
    ("Zscaler", "https://zscaler.com", "https://www.zscaler.com/careers", "zscaler", "zscaler", Tier.TIER2),
    ("Toast", "https://toasttab.com", "https://careers.toasttab.com/", "toasttab", "toaborasttab", Tier.TIER2),
    ("Coupang", "https://coupang.com", "https://www.coupang.jobs/", "nicklockwood", "Coupang", Tier.TIER2),
    ("Rivian", "https://rivian.com", "https://careers.rivian.com/", "rivian", "Rivian", Tier.TIER2),
    ("Lucid Motors", "https://lucidmotors.com", "https://www.lucidmotors.com/careers", "nicklockwood", "LucidMotors", Tier.TIER2),
    # ═══════════════════════════════════════════════════════
    # TIER 3 — Dev Tools, Open Source, Emerging Startups (30 companies)
    # ═══════════════════════════════════════════════════════
    ("Vercel", "https://vercel.com", "https://vercel.com/careers", "vercel", "vercel", Tier.TIER3),
    ("Supabase", "https://supabase.com", "https://supabase.com/careers", "supabase", "supabase", Tier.TIER3),
    ("Railway", "https://railway.app", "https://railway.app/careers", "railwayapp", "Railway", Tier.TIER3),
    ("Linear", "https://linear.app", "https://linear.app/careers", "linearapp", "linear", Tier.TIER3),
    ("Replit", "https://replit.com", "https://replit.com/site/careers", "replit", "Replit", Tier.TIER3),
    ("PostHog", "https://posthog.com", "https://posthog.com/careers", "PostHog", "PostHog", Tier.TIER3),
    ("Grafana Labs", "https://grafana.com", "https://grafana.com/about/careers/", "grafana", "grafana", Tier.TIER3),
    ("Temporal", "https://temporal.io", "https://temporal.io/careers", "temporalio", "temporalio", Tier.TIER3),
    ("PlanetScale", "https://planetscale.com", "https://planetscale.com/careers", "planetscale", "PlanetScale", Tier.TIER3),
    ("Neon", "https://neon.tech", "https://neon.tech/careers", "neondatabase", "neaborondatabase", Tier.TIER3),
    ("Fly.io", "https://fly.io", "https://fly.io/jobs/", "superfly", "flydotio", Tier.TIER3),
    ("Deno", "https://deno.com", "https://deno.com/jobs", "denoland", "daboreno_land", Tier.TIER3),
    ("Turso", "https://turso.tech", "https://turso.tech/careers", "tursodatabase", "taborursodatabase", Tier.TIER3),
    ("Mistral AI", "https://mistral.ai", "https://mistral.ai/careers/", "mistralai", "MistralAI", Tier.TIER3),
    ("Cohere", "https://cohere.com", "https://cohere.com/careers", "cohere-ai", "CohereForAI", Tier.TIER3),
    ("Hugging Face", "https://huggingface.co", "https://apply.workable.com/huggingface/", "huggingface", "huggingface", Tier.TIER3),
    ("Weights & Biases", "https://wandb.ai", "https://boards.greenhouse.io/wandb", "wandb", "Weights_Biases", Tier.TIER3),
    ("LangChain", "https://langchain.com", "https://www.langchain.com/careers", "langchain-ai", "LangChainAI", Tier.TIER3),
    ("Cursor", "https://cursor.com", "https://www.cursor.com/careers", "getcursor", "cursor_ai", Tier.TIER3),
    ("Perplexity", "https://perplexity.ai", "https://www.perplexity.ai/hub/careers", "nicklockwood", "peraborplexity_ai", Tier.TIER3),
    ("Together AI", "https://together.ai", "https://www.together.ai/careers", "togethercomputer", "togethercompute", Tier.TIER3),
    ("Sentry", "https://sentry.io", "https://sentry.io/careers/", "getsentry", "getsentry", Tier.TIER3),
    ("Retool", "https://retool.com", "https://retool.com/careers", "tryretool", "retaborool", Tier.TIER3),
    ("Resend", "https://resend.com", "https://resend.com/careers", "resend", "resaborendlabs", Tier.TIER3),
    ("Cal.com", "https://cal.com", "https://cal.com/jobs", "calcom", "calaborcom", Tier.TIER3),
    ("Clerk", "https://clerk.com", "https://clerk.com/careers", "clerk", "ClerkDev", Tier.TIER3),
    ("Convex", "https://convex.dev", "https://www.convex.dev/careers", "get-convex", "convaborex_dev", Tier.TIER3),
    ("Axiom", "https://axiom.co", "https://axiom.co/careers", "axiomhq", "AxiomFM", Tier.TIER3),
    ("Upstash", "https://upstash.com", "https://upstash.com/careers", "upstash", "upaborstash", Tier.TIER3),
    ("Trigger.dev", "https://trigger.dev", "https://trigger.dev/careers", "triggerdotdev", "triggaborerdotdev", Tier.TIER3),
]


async def seed_companies() -> int:
    """Insert placeholder companies if the table is empty. Returns count."""
    async with get_session() as session:
        from sqlalchemy import select, func as sqla_func

        count = (await session.execute(select(sqla_func.count(Company.id)))).scalar() or 0
        if count > 0:
            logger.info("Companies table already has %d rows — skipping seed.", count)
            return count

        for name, site, careers, gh, tw, tier in _SEED_COMPANIES:
            session.add(
                Company(
                    company_name=name,
                    website=site,
                    careers_url=careers,
                    github_org=gh,
                    twitter_handle=tw,
                    tier=tier,
                )
            )
        logger.info("Seeded %d placeholder companies.", len(_SEED_COMPANIES))
        return len(_SEED_COMPANIES)


# ── CSV Import ────────────────────────────────────────────────


async def import_csv(path: str | Path, batch_size: int = 1000) -> int:
    """
    Bulk-import companies from a CSV.

    Expected columns (header row required):
        company_name, website, careers_url, github_org, twitter_handle, tier

    Returns the number of rows imported.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    imported = 0
    batch: list[Company] = []

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            tier_val = int(row.get("tier", Tier.TIER3))
            batch.append(
                Company(
                    company_name=row["company_name"],
                    website=row.get("website", ""),
                    careers_url=row.get("careers_url", ""),
                    github_org=row.get("github_org", ""),
                    twitter_handle=row.get("twitter_handle", ""),
                    tier=tier_val,
                )
            )

            if len(batch) >= batch_size:
                async with get_session() as session:
                    session.add_all(batch)
                imported += len(batch)
                batch = []
                logger.info("Imported %d companies so far ...", imported)

    # Flush remainder
    if batch:
        async with get_session() as session:
            session.add_all(batch)
        imported += len(batch)

    logger.info("CSV import complete — %d companies imported from %s.", imported, path)
    return imported

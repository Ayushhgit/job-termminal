"""Seed data generator — creates realistic placeholder companies for testing."""

from __future__ import annotations

import asyncio
import csv
import random
import logging
from pathlib import Path

from database.db import init_db, get_session, import_csv
from database.models import Company, HiringHistory, Tier

logger = logging.getLogger(__name__)

# ── Expanded company list for testing ─────────────────────────

TIER1_COMPANIES = [
    ("Google", "https://google.com", "https://careers.google.com", "google", "Google"),
    ("Microsoft", "https://microsoft.com", "https://careers.microsoft.com", "microsoft", "Microsoft"),
    ("Apple", "https://apple.com", "https://jobs.apple.com", "apple", "Apple"),
    ("Meta", "https://meta.com", "https://metacareers.com", "facebook", "Meta"),
    ("Amazon", "https://amazon.com", "https://amazon.jobs", "amzn", "AmazonNews"),
    ("Netflix", "https://netflix.com", "https://jobs.netflix.com", "Netflix", "netflix"),
    ("Tesla", "https://tesla.com", "https://tesla.com/careers", "teslamotors", "Tesla"),
    ("OpenAI", "https://openai.com", "https://openai.com/careers", "openai", "OpenAI"),
    ("Stripe", "https://stripe.com", "https://stripe.com/jobs", "stripe", "stripe"),
    ("Anthropic", "https://anthropic.com", "https://anthropic.com/careers", "anthropics", "AnthropicAI"),
    ("NVIDIA", "https://nvidia.com", "https://nvidia.com/careers", "NVIDIA", "nvidia"),
    ("Salesforce", "https://salesforce.com", "https://salesforce.com/careers", "salesforce", "salesforce"),
    ("Adobe", "https://adobe.com", "https://adobe.com/careers", "adobe", "Adobe"),
    ("Uber", "https://uber.com", "https://uber.com/careers", "uber", "Uber"),
    ("Airbnb", "https://airbnb.com", "https://careers.airbnb.com", "airbnb", "Airbnb"),
    ("Spotify", "https://spotify.com", "https://lifeatspotify.com", "spotify", "Spotify"),
    ("Twitter/X", "https://x.com", "https://careers.twitter.com", "twitter", "x"),
    ("Coinbase", "https://coinbase.com", "https://coinbase.com/careers", "coinbase", "coinbase"),
    ("Palantir", "https://palantir.com", "https://palantir.com/careers", "palantir", "PalantirTech"),
    ("Databricks", "https://databricks.com", "https://databricks.com/careers", "databricks", "databricks"),
]

TIER2_COMPANIES = [
    ("Shopify", "https://shopify.com", "https://shopify.com/careers", "Shopify", "Shopify"),
    ("Datadog", "https://datadoghq.com", "https://datadoghq.com/careers", "DataDog", "datadoghq"),
    ("Snowflake", "https://snowflake.com", "https://careers.snowflake.com", "snowflakedb", "SnowflakeDB"),
    ("Cloudflare", "https://cloudflare.com", "https://cloudflare.com/careers", "cloudflare", "Cloudflare"),
    ("HashiCorp", "https://hashicorp.com", "https://hashicorp.com/careers", "hashicorp", "HashiCorp"),
    ("MongoDB", "https://mongodb.com", "https://mongodb.com/careers", "mongodb", "MongoDB"),
    ("Elastic", "https://elastic.co", "https://elastic.co/careers", "elastic", "elastic"),
    ("Twilio", "https://twilio.com", "https://twilio.com/company/jobs", "twilio", "twilio"),
    ("Square", "https://squareup.com", "https://squareup.com/careers", "square", "Square"),
    ("Figma", "https://figma.com", "https://figma.com/careers", "figma", "figma"),
]

TIER3_COMPANIES = [
    ("Notion", "https://notion.so", "https://notion.so/careers", "makenotion", "NotionHQ"),
    ("Linear", "https://linear.app", "https://linear.app/careers", "linearapp", "linear"),
    ("Vercel", "https://vercel.com", "https://vercel.com/careers", "vercel", "vercel"),
    ("Supabase", "https://supabase.com", "https://supabase.com/careers", "supabase", "supabase"),
    ("Railway", "https://railway.app", "https://railway.app/careers", "railwayapp", "Railway"),
    ("Deno", "https://deno.com", "https://deno.com/careers", "denoland", "daboreno_land"),
    ("Turso", "https://turso.tech", "https://turso.tech/careers", "tursodatabase", "taborursodatabase"),
    ("Neon", "https://neon.tech", "https://neon.tech/careers", "neondatabase", "neondatabase"),
    ("Resend", "https://resend.com", "https://resend.com/careers", "resendlabs", "resaborendlabs"),
    ("Cal.com", "https://cal.com", "https://cal.com/careers", "calcom", "calaborcom"),
]


async def seed_full_dataset() -> int:
    """Seed the database with the expanded company list and hiring history."""
    await init_db()

    count = 0
    async with get_session() as session:
        # Check if already seeded
        from sqlalchemy import select, func as sqla_func
        existing = (
            await session.execute(select(sqla_func.count(Company.id)))
        ).scalar() or 0

        if existing > 0:
            logger.info("Database already has %d companies.", existing)
            return existing

        # Insert all tiers
        for name, site, careers, gh, tw in TIER1_COMPANIES:
            session.add(Company(
                company_name=name, website=site, careers_url=careers,
                github_org=gh, twitter_handle=tw, tier=Tier.TIER1,
            ))
            count += 1

        for name, site, careers, gh, tw in TIER2_COMPANIES:
            session.add(Company(
                company_name=name, website=site, careers_url=careers,
                github_org=gh, twitter_handle=tw, tier=Tier.TIER2,
            ))
            count += 1

        for name, site, careers, gh, tw in TIER3_COMPANIES:
            session.add(Company(
                company_name=name, website=site, careers_url=careers,
                github_org=gh, twitter_handle=tw, tier=Tier.TIER3,
            ))
            count += 1

    # Add some hiring history for Tier 1 companies
    async with get_session() as session:
        from sqlalchemy import select
        t1 = (await session.execute(
            select(Company).where(Company.tier == Tier.TIER1)
        )).scalars().all()

        for company in t1:
            # Simulate that big companies have historically hired interns
            for year in (2023, 2024, 2025):
                for month in (1, 6):  # Jan and June hiring
                    session.add(HiringHistory(
                        company_id=company.id,
                        role="Software Engineering Intern",
                        month=month,
                        year=year,
                    ))

    logger.info("Seeded %d companies with hiring history.", count)
    return count


def generate_csv(path: str = "sample_companies.csv", num_companies: int = 100) -> str:
    """Generate a sample CSV file for testing bulk import."""
    p = Path(path)
    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "company_name", "website", "careers_url", "github_org", "twitter_handle", "tier",
        ])
        writer.writeheader()

        for i in range(num_companies):
            tier = 1 if i < 10 else (2 if i < 40 else 3)
            writer.writerow({
                "company_name": f"Company_{i:04d}",
                "website": f"https://company{i}.com",
                "careers_url": f"https://company{i}.com/careers",
                "github_org": f"company{i}",
                "twitter_handle": f"company{i}",
                "tier": tier,
            })

    logger.info("Generated sample CSV: %s (%d companies)", p, num_companies)
    return str(p)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_full_dataset())
    print("Seeding complete!")

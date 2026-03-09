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
    # Format: (name, website, careers_url, github_org, twitter_handle, tier, country)
    # ═══════════════════════════════════════════════════════
    # TIER 1 — FAANG, Top AI/ML, Major Unicorns (35 companies)
    # ═══════════════════════════════════════════════════════
    ("Google", "https://google.com", "https://www.google.com/about/careers/applications/", "google", "Google", Tier.TIER1, "Global"),
    ("Microsoft", "https://microsoft.com", "https://careers.microsoft.com/", "microsoft", "Microsoft", Tier.TIER1, "Global"),
    ("Apple", "https://apple.com", "https://jobs.apple.com/", "apple", "Apple", Tier.TIER1, "Global"),
    ("Meta", "https://meta.com", "https://www.metacareers.com/", "facebook", "Meta", Tier.TIER1, "Global"),
    ("Amazon", "https://amazon.com", "https://www.amazon.jobs/", "amzn", "AmazonNews", Tier.TIER1, "Global"),
    ("Netflix", "https://netflix.com", "https://jobs.netflix.com/", "Netflix", "netflix", Tier.TIER1, "Global"),
    ("NVIDIA", "https://nvidia.com", "https://www.nvidia.com/en-us/about-nvidia/careers/", "NVIDIA", "nvidia", Tier.TIER1, "Global"),
    ("Tesla", "https://tesla.com", "https://www.tesla.com/careers", "teslamotors", "Tesla", Tier.TIER1, "Global"),
    ("OpenAI", "https://openai.com", "https://openai.com/careers/", "openai", "OpenAI", Tier.TIER1, "Global"),
    ("Anthropic", "https://anthropic.com", "https://www.anthropic.com/careers", "anthropics", "AnthropicAI", Tier.TIER1, "Global"),
    ("DeepMind", "https://deepmind.google", "https://deepmind.google/about/careers/", "google-deepmind", "GoogleDeepMind", Tier.TIER1, "Global"),
    ("Stripe", "https://stripe.com", "https://stripe.com/jobs", "stripe", "stripe", Tier.TIER1, "Global"),
    ("Salesforce", "https://salesforce.com", "https://careers.salesforce.com/", "salesforce", "salesforce", Tier.TIER1, "Global"),
    ("Adobe", "https://adobe.com", "https://careers.adobe.com/", "adobe", "Adobe", Tier.TIER1, "Global"),
    ("Intel", "https://intel.com", "https://jobs.intel.com/", "intel", "intel", Tier.TIER1, "Global"),
    ("IBM", "https://ibm.com", "https://www.ibm.com/careers", "IBM", "IBM", Tier.TIER1, "Global"),
    ("Oracle", "https://oracle.com", "https://www.oracle.com/careers/", "oracle", "Oracle", Tier.TIER1, "Global"),
    ("Uber", "https://uber.com", "https://www.uber.com/us/en/careers/", "uber", "Uber", Tier.TIER1, "Global"),
    ("Airbnb", "https://airbnb.com", "https://careers.airbnb.com/", "airbnb", "Airbnb", Tier.TIER1, "Global"),
    ("Spotify", "https://spotify.com", "https://www.lifeatspotify.com/jobs", "spotify", "Spotify", Tier.TIER1, "Global"),
    ("LinkedIn", "https://linkedin.com", "https://careers.linkedin.com/", "linkedin", "LinkedIn", Tier.TIER1, "Global"),
    ("Twitter", "https://x.com", "https://careers.twitter.com/", "twitter", "X", Tier.TIER1, "Global"),
    ("Snap", "https://snap.com", "https://snap.com/en-US/jobs", "Snapchat", "Snapchat", Tier.TIER1, "Global"),
    ("Pinterest", "https://pinterest.com", "https://www.pinterestcareers.com/", "pinterest", "Pinterest", Tier.TIER1, "Global"),
    ("Coinbase", "https://coinbase.com", "https://www.coinbase.com/careers", "coinbase", "coinbase", Tier.TIER1, "Global"),
    ("Block", "https://block.xyz", "https://block.xyz/careers", "square", "blocks", Tier.TIER1, "Global"),
    ("Qualcomm", "https://qualcomm.com", "https://www.qualcomm.com/company/careers", "qualcomm", "Qualcomm", Tier.TIER1, "Global"),
    ("AMD", "https://amd.com", "https://www.amd.com/en/corporate/careers.html", "GPUOpen-LibrariesAndSDKs", "AMD", Tier.TIER1, "Global"),
    ("Palantir", "https://palantir.com", "https://www.palantir.com/careers/", "palantir", "PalantirTech", Tier.TIER1, "Global"),
    ("Databricks", "https://databricks.com", "https://www.databricks.com/company/careers", "databricks", "databricks", Tier.TIER1, "Global"),
    ("ByteDance", "https://bytedance.com", "https://jobs.bytedance.com/", "nicklockwood", "BytedanceTalk", Tier.TIER1, "Global"),
    ("Samsung", "https://samsung.com", "https://www.samsung.com/us/careers/", "nicklockwood", "SamsungMobile", Tier.TIER1, "Global"),
    ("Cisco", "https://cisco.com", "https://jobs.cisco.com/", "cisco", "Cisco", Tier.TIER1, "Global"),
    ("VMware", "https://vmware.com", "https://careers.vmware.com/", "vmware", "VMware", Tier.TIER1, "Global"),
    ("SAP", "https://sap.com", "https://jobs.sap.com/", "SAP", "SAP", Tier.TIER1, "Global"),
    # ═══════════════════════════════════════════════════════
    # TIER 1 — Top Indian Tech Companies (15 companies)
    # ═══════════════════════════════════════════════════════
    ("Flipkart", "https://flipkart.com", "https://www.flipkartcareers.com/", "nicklockwood", "Flipkart", Tier.TIER1, "India"),
    ("Infosys", "https://infosys.com", "https://www.infosys.com/careers/", "nicklockwood", "Infosys", Tier.TIER1, "India"),
    ("TCS", "https://tcs.com", "https://www.tcs.com/careers", "nicklockwood", "TCS", Tier.TIER1, "India"),
    ("Wipro", "https://wipro.com", "https://careers.wipro.com/", "nicklockwood", "Wipro", Tier.TIER1, "India"),
    ("HCL Technologies", "https://hcltech.com", "https://www.hcltech.com/careers", "nicklockwood", "haborcltech", Tier.TIER1, "India"),
    ("Reliance Jio", "https://jio.com", "https://careers.jio.com/", "nicklockwood", "reliaborancejio", Tier.TIER1, "India"),
    ("Paytm", "https://paytm.com", "https://jobs.lever.co/paytm", "nicklockwood", "Paytm", Tier.TIER1, "India"),
    ("Zomato", "https://zomato.com", "https://www.zomato.com/careers", "nicklockwood", "zomato", Tier.TIER1, "India"),
    ("Swiggy", "https://swiggy.com", "https://careers.swiggy.com/", "nicklockwood", "Swiggy", Tier.TIER1, "India"),
    ("Razorpay", "https://razorpay.com", "https://razorpay.com/jobs/", "razorpay", "Razorpay", Tier.TIER1, "India"),
    ("Ola", "https://olacabs.com", "https://www.olacabs.com/careers", "nicklockwood", "Aborla_cabs", Tier.TIER1, "India"),
    ("PhonePe", "https://phonepe.com", "https://www.phonepe.com/careers/", "nicklockwood", "PhonePe", Tier.TIER1, "India"),
    ("Freshworks", "https://freshworks.com", "https://www.freshworks.com/company/careers/", "freshdesk", "FreshworksInc", Tier.TIER1, "India"),
    ("Zoho", "https://zoho.com", "https://www.zoho.com/careers/", "nicklockwood", "Zoho", Tier.TIER1, "India"),
    ("Dream11", "https://dream11.com", "https://www.dreamsports.group/careers", "nicklockwood", "Dream11", Tier.TIER1, "India"),
    # ═══════════════════════════════════════════════════════
    # TIER 2 — Growth-Stage Tech (40 global companies)
    # ═══════════════════════════════════════════════════════
    ("Shopify", "https://shopify.com", "https://www.shopify.com/careers", "Shopify", "Shopify", Tier.TIER2, "Global"),
    ("Datadog", "https://datadoghq.com", "https://careers.datadoghq.com/", "DataDog", "datadoghq", Tier.TIER2, "Global"),
    ("Snowflake", "https://snowflake.com", "https://careers.snowflake.com/", "snowflakedb", "SnowflakeDB", Tier.TIER2, "Global"),
    ("Cloudflare", "https://cloudflare.com", "https://www.cloudflare.com/careers/", "cloudflare", "Cloudflare", Tier.TIER2, "Global"),
    ("Twilio", "https://twilio.com", "https://www.twilio.com/company/jobs", "twilio", "twilio", Tier.TIER2, "Global"),
    ("Figma", "https://figma.com", "https://www.figma.com/careers/", "figma", "figma", Tier.TIER2, "Global"),
    ("Canva", "https://canva.com", "https://www.canva.com/careers/", "canva", "canva", Tier.TIER2, "Global"),
    ("Slack", "https://slack.com", "https://slack.com/careers", "slackapi", "SlackHQ", Tier.TIER2, "Global"),
    ("Atlassian", "https://atlassian.com", "https://www.atlassian.com/company/careers", "atlassian", "Atlassian", Tier.TIER2, "Global"),
    ("GitLab", "https://gitlab.com", "https://about.gitlab.com/jobs/", "gitlabhq", "gitlab", Tier.TIER2, "Global"),
    ("GitHub", "https://github.com", "https://github.com/about/careers", "github", "github", Tier.TIER2, "Global"),
    ("Elastic", "https://elastic.co", "https://www.elastic.co/careers/", "elastic", "elastic", Tier.TIER2, "Global"),
    ("MongoDB", "https://mongodb.com", "https://www.mongodb.com/company/careers", "mongodb", "MongoDB", Tier.TIER2, "Global"),
    ("Confluent", "https://confluent.io", "https://www.confluent.io/careers/", "confluentinc", "confluentinc", Tier.TIER2, "Global"),
    ("HashiCorp", "https://hashicorp.com", "https://www.hashicorp.com/careers", "hashicorp", "HashiCorp", Tier.TIER2, "Global"),
    ("Splunk", "https://splunk.com", "https://www.splunk.com/en_us/careers.html", "splunk", "splunk", Tier.TIER2, "Global"),
    ("Palo Alto Networks", "https://paloaltonetworks.com", "https://jobs.paloaltonetworks.com/", "PaloAltoNetworks", "PaloAltoNtwks", Tier.TIER2, "Global"),
    ("CrowdStrike", "https://crowdstrike.com", "https://www.crowdstrike.com/careers/", "CrowdStrike", "CrowdStrike", Tier.TIER2, "Global"),
    ("Plaid", "https://plaid.com", "https://plaid.com/careers/", "plaid", "PlaidInc", Tier.TIER2, "Global"),
    ("Rippling", "https://rippling.com", "https://www.rippling.com/careers", "Rippling", "Rippling", Tier.TIER2, "Global"),
    ("Scale AI", "https://scale.com", "https://scale.com/careers", "scaleapi", "scale_AI", Tier.TIER2, "Global"),
    ("Anduril", "https://anduril.com", "https://www.anduril.com/careers/", "anduril", "anduriltech", Tier.TIER2, "Global"),
    ("Ramp", "https://ramp.com", "https://ramp.com/careers", "RampHQ", "tryramp", Tier.TIER2, "Global"),
    ("Brex", "https://brex.com", "https://www.brex.com/careers", "brexhq", "brexhq", Tier.TIER2, "Global"),
    ("Robinhood", "https://robinhood.com", "https://careers.robinhood.com/", "robinhoodapi", "RobinhoodApp", Tier.TIER2, "Global"),
    ("DoorDash", "https://doordash.com", "https://careers.doordash.com/", "doordash", "DoorDash", Tier.TIER2, "Global"),
    ("Instacart", "https://instacart.com", "https://instacart.careers/", "instacart", "Instacart", Tier.TIER2, "Global"),
    ("Lyft", "https://lyft.com", "https://www.lyft.com/careers", "lyft", "lyft", Tier.TIER2, "Global"),
    ("Reddit", "https://reddit.com", "https://www.redditinc.com/careers", "reddit", "Reddit", Tier.TIER2, "Global"),
    ("Discord", "https://discord.com", "https://discord.com/careers", "discord", "discord", Tier.TIER2, "Global"),
    ("Notion", "https://notion.so", "https://www.notion.so/careers", "makenotion", "NotionHQ", Tier.TIER2, "Global"),
    ("Airtable", "https://airtable.com", "https://airtable.com/careers", "Airtable", "airtable", Tier.TIER2, "Global"),
    ("Grammarly", "https://grammarly.com", "https://www.grammarly.com/careers", "grammarly", "Grammarly", Tier.TIER2, "Global"),
    ("HubSpot", "https://hubspot.com", "https://www.hubspot.com/careers", "HubSpot", "HubSpot", Tier.TIER2, "Global"),
    ("Okta", "https://okta.com", "https://www.okta.com/company/careers/", "okta", "okta", Tier.TIER2, "Global"),
    ("Zscaler", "https://zscaler.com", "https://www.zscaler.com/careers", "zscaler", "zscaler", Tier.TIER2, "Global"),
    ("Toast", "https://toasttab.com", "https://careers.toasttab.com/", "toasttab", "toasttab", Tier.TIER2, "Global"),
    ("Coupang", "https://coupang.com", "https://www.coupang.jobs/", "nicklockwood", "Coupang", Tier.TIER2, "Global"),
    ("Rivian", "https://rivian.com", "https://careers.rivian.com/", "rivian", "Rivian", Tier.TIER2, "Global"),
    ("Lucid Motors", "https://lucidmotors.com", "https://www.lucidmotors.com/careers", "nicklockwood", "LucidMotors", Tier.TIER2, "Global"),
    # ═══════════════════════════════════════════════════════
    # TIER 2 — Indian Growth Startups (20 companies)
    # ═══════════════════════════════════════════════════════
    ("CRED", "https://cred.club", "https://careers.cred.club/", "nicklockwood", "CABORRED_club", Tier.TIER2, "India"),
    ("Meesho", "https://meesho.com", "https://careers.meesho.com/", "nicklockwood", "Meesho", Tier.TIER2, "India"),
    ("Zerodha", "https://zerodha.com", "https://zerodha.com/careers/", "zerodha", "zeaborrodhaonline", Tier.TIER2, "India"),
    ("Groww", "https://groww.in", "https://groww.in/careers", "nicklockwood", "growaborwin", Tier.TIER2, "India"),
    ("Nykaa", "https://nykaa.com", "https://careers.nykaa.com/", "nicklockwood", "MyNykaa", Tier.TIER2, "India"),
    ("upGrad", "https://upgrad.com", "https://www.upgrad.com/careers/", "nicklockwood", "upGrad", Tier.TIER2, "India"),
    ("Unacademy", "https://unacademy.com", "https://unacademy.com/careers", "nicklockwood", "unacaborademy", Tier.TIER2, "India"),
    ("ShareChat", "https://sharechat.com", "https://sharechat.com/careers", "nicklockwood", "ShareChat", Tier.TIER2, "India"),
    ("Lenskart", "https://lenskart.com", "https://www.lenskart.com/careers", "nicklockwood", "Lenskart", Tier.TIER2, "India"),
    ("Urban Company", "https://urbancompany.com", "https://careers.urbancompany.com/", "nicklockwood", "UrbanCompany", Tier.TIER2, "India"),
    ("PolicyBazaar", "https://policybazaar.com", "https://careers.policybazaar.com/", "nicklockwood", "policybaborazaar", Tier.TIER2, "India"),
    ("Cars24", "https://cars24.com", "https://www.cars24.com/careers/", "nicklockwood", "CARS24", Tier.TIER2, "India"),
    ("Delhivery", "https://delhivery.com", "https://www.delhivery.com/careers/", "nicklockwood", "Delhivery", Tier.TIER2, "India"),
    ("Pine Labs", "https://pinelabs.com", "https://www.pinelabs.com/careers", "nicklockwood", "PineLabsIn", Tier.TIER2, "India"),
    ("Coinswitch", "https://coinswitch.co", "https://coinswitch.co/careers", "nicklockwood", "CoinSwitch", Tier.TIER2, "India"),
    ("Jupiter", "https://jupiter.money", "https://jupiter.money/careers/", "nicklockwood", "JupaboriterMoney", Tier.TIER2, "India"),
    ("Slice", "https://sliceit.com", "https://sliceit.com/careers", "nicklockwood", "slicaboreit_app", Tier.TIER2, "India"),
    ("MakeMyTrip", "https://makemytrip.com", "https://careers.makemytrip.com/", "nicklockwood", "makemytrip", Tier.TIER2, "India"),
    ("InMobi", "https://inmobi.com", "https://www.inmobi.com/company/careers", "nicklockwood", "InMobi", Tier.TIER2, "India"),
    ("Cure.fit", "https://curefit.com", "https://www.cure.fit/careers", "nicklockwood", "caborurefit", Tier.TIER2, "India"),
    # ═══════════════════════════════════════════════════════
    # TIER 3 — Dev Tools, Open Source, Emerging Global Startups (30 companies)
    # ═══════════════════════════════════════════════════════
    ("Vercel", "https://vercel.com", "https://vercel.com/careers", "vercel", "vercel", Tier.TIER3, "Global"),
    ("Supabase", "https://supabase.com", "https://supabase.com/careers", "supabase", "supabase", Tier.TIER3, "Global"),
    ("Railway", "https://railway.app", "https://railway.app/careers", "railwayapp", "Railway", Tier.TIER3, "Global"),
    ("Linear", "https://linear.app", "https://linear.app/careers", "linearapp", "linear", Tier.TIER3, "Global"),
    ("Replit", "https://replit.com", "https://replit.com/site/careers", "replit", "Replit", Tier.TIER3, "Global"),
    ("PostHog", "https://posthog.com", "https://posthog.com/careers", "PostHog", "PostHog", Tier.TIER3, "Global"),
    ("Grafana Labs", "https://grafana.com", "https://grafana.com/about/careers/", "grafana", "grafana", Tier.TIER3, "Global"),
    ("Temporal", "https://temporal.io", "https://temporal.io/careers", "temporalio", "temporalio", Tier.TIER3, "Global"),
    ("PlanetScale", "https://planetscale.com", "https://planetscale.com/careers", "planetscale", "PlanetScale", Tier.TIER3, "Global"),
    ("Neon", "https://neon.tech", "https://neon.tech/careers", "neondatabase", "neondatabase", Tier.TIER3, "Global"),
    ("Fly.io", "https://fly.io", "https://fly.io/jobs/", "superfly", "flydotio", Tier.TIER3, "Global"),
    ("Deno", "https://deno.com", "https://deno.com/jobs", "denoland", "denoland", Tier.TIER3, "Global"),
    ("Turso", "https://turso.tech", "https://turso.tech/careers", "tursodatabase", "tursodatabase", Tier.TIER3, "Global"),
    ("Mistral AI", "https://mistral.ai", "https://mistral.ai/careers/", "mistralai", "MistralAI", Tier.TIER3, "Global"),
    ("Cohere", "https://cohere.com", "https://cohere.com/careers", "cohere-ai", "CohereForAI", Tier.TIER3, "Global"),
    ("Hugging Face", "https://huggingface.co", "https://apply.workable.com/huggingface/", "huggingface", "huggingface", Tier.TIER3, "Global"),
    ("Weights & Biases", "https://wandb.ai", "https://boards.greenhouse.io/wandb", "wandb", "Weights_Biases", Tier.TIER3, "Global"),
    ("LangChain", "https://langchain.com", "https://www.langchain.com/careers", "langchain-ai", "LangChainAI", Tier.TIER3, "Global"),
    ("Cursor", "https://cursor.com", "https://www.cursor.com/careers", "getcursor", "cursor_ai", Tier.TIER3, "Global"),
    ("Perplexity", "https://perplexity.ai", "https://www.perplexity.ai/hub/careers", "nicklockwood", "perplexity_ai", Tier.TIER3, "Global"),
    ("Together AI", "https://together.ai", "https://www.together.ai/careers", "togethercomputer", "togethercompute", Tier.TIER3, "Global"),
    ("Sentry", "https://sentry.io", "https://sentry.io/careers/", "getsentry", "getsentry", Tier.TIER3, "Global"),
    ("Retool", "https://retool.com", "https://retool.com/careers", "tryretool", "retool", Tier.TIER3, "Global"),
    ("Resend", "https://resend.com", "https://resend.com/careers", "resend", "resendlabs", Tier.TIER3, "Global"),
    ("Cal.com", "https://cal.com", "https://cal.com/jobs", "calcom", "calcom", Tier.TIER3, "Global"),
    ("Clerk", "https://clerk.com", "https://clerk.com/careers", "clerk", "ClerkDev", Tier.TIER3, "Global"),
    ("Convex", "https://convex.dev", "https://www.convex.dev/careers", "get-convex", "convex_dev", Tier.TIER3, "Global"),
    ("Axiom", "https://axiom.co", "https://axiom.co/careers", "axiomhq", "AxiomFM", Tier.TIER3, "Global"),
    ("Upstash", "https://upstash.com", "https://upstash.com/careers", "upstash", "upstash", Tier.TIER3, "Global"),
    ("Trigger.dev", "https://trigger.dev", "https://trigger.dev/careers", "triggerdotdev", "triggerdotdev", Tier.TIER3, "Global"),
    # ═══════════════════════════════════════════════════════
    # TIER 3 — Emerging Indian Startups (20 companies)
    # ═══════════════════════════════════════════════════════
    ("Postman", "https://postman.com", "https://www.postman.com/company/careers/", "postmanlabs", "getpostman", Tier.TIER3, "India"),
    ("Hasura", "https://hasura.io", "https://hasura.io/careers/", "hasura", "HasuraHQ", Tier.TIER3, "India"),
    ("Chargebee", "https://chargebee.com", "https://www.chargebee.com/company/careers/", "chargebee", "chargebee", Tier.TIER3, "India"),
    ("Darwinbox", "https://darwinbox.com", "https://www.darwinbox.com/careers", "nicklockwood", "Darwinbox", Tier.TIER3, "India"),
    ("BrowserStack", "https://browserstack.com", "https://www.browserstack.com/careers", "nicklockwood", "browserstack", Tier.TIER3, "India"),
    ("Atlan", "https://atlan.com", "https://www.atlan.com/careers/", "atlanhq", "AtlanHQ", Tier.TIER3, "India"),
    ("Hevo Data", "https://hevodata.com", "https://hevodata.com/careers/", "nicklockwood", "HevoData", Tier.TIER3, "India"),
    ("Scaler", "https://scaler.com", "https://www.scaler.com/careers/", "nicklockwood", "scaboraler_by_IA", Tier.TIER3, "India"),
    ("Coding Ninjas", "https://codingninjas.com", "https://www.codingninjas.com/careers", "nicklockwood", "CodingNinjas", Tier.TIER3, "India"),
    ("Razorpay X", "https://razorpay.com/x/", "https://razorpay.com/jobs/", "razorpay", "Razorpay", Tier.TIER3, "India"),
    ("LeadSquared", "https://leadsquared.com", "https://www.leadsquared.com/careers/", "nicklockwood", "LeadSquared", Tier.TIER3, "India"),
    ("CleverTap", "https://clevertap.com", "https://clevertap.com/careers/", "nicklockwood", "CleverTap", Tier.TIER3, "India"),
    ("WebEngage", "https://webengage.com", "https://webengage.com/careers/", "nicklockwood", "WebEngage", Tier.TIER3, "India"),
    ("Yellowai", "https://yellow.ai", "https://yellow.ai/careers/", "nicklockwood", "yellowaborai", Tier.TIER3, "India"),
    ("Mindtickle", "https://mindtickle.com", "https://www.mindtickle.com/careers/", "nicklockwood", "Mindtickle", Tier.TIER3, "India"),
    ("Zetwerk", "https://zetwerk.com", "https://www.zetwerk.com/careers/", "nicklockwood", "Zetwerk", Tier.TIER3, "India"),
    ("Shiprocket", "https://shiprocket.in", "https://www.shiprocket.in/careers/", "nicklockwood", "Shiprocket", Tier.TIER3, "India"),
    ("Pocket FM", "https://pocketfm.com", "https://www.pocketfm.com/careers/", "nicklockwood", "PocketFM", Tier.TIER3, "India"),
    ("Park+", "https://parkplus.io", "https://www.parkplus.io/careers", "nicklockwood", "ParkPlusIO", Tier.TIER3, "India"),
    ("Apna", "https://apna.co", "https://apna.co/careers", "nicklockwood", "apabornahq", Tier.TIER3, "India"),
]


async def seed_companies() -> int:
    """Insert placeholder companies if the table is empty. Returns count."""
    async with get_session() as session:
        from sqlalchemy import select, func as sqla_func

        count = (await session.execute(select(sqla_func.count(Company.id)))).scalar() or 0
        if count > 0:
            logger.info("Companies table already has %d rows — skipping seed.", count)
            return count

        for name, site, careers, gh, tw, tier, country in _SEED_COMPANIES:
            session.add(
                Company(
                    company_name=name,
                    website=site,
                    careers_url=careers,
                    github_org=gh,
                    twitter_handle=tw,
                    tier=tier,
                    country=country,
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

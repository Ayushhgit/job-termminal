"""Seed realistic sample job/internship listings for demo purposes."""

from __future__ import annotations

import logging

from database.db import get_session
from database.models import Job
from sqlalchemy import select, func as sqla_func

logger = logging.getLogger(__name__)

# Format: (company_name, title, location, job_type, description, application_url, salary_range)
_SEED_JOBS = [
    # ── Indian Companies — Internships ───────────────────────
    ("Flipkart", "Software Engineering Intern", "Bangalore, India", "internship",
     "Work on large-scale distributed systems powering India's largest e-commerce platform. Build microservices handling millions of transactions.",
     "https://www.flipkartcareers.com/#!/joblist", "₹40K-60K/month"),

    ("Razorpay", "Backend Engineering Intern", "Bangalore, India", "internship",
     "Join the payments team to build scalable APIs processing billions in transactions. Work with Go, Ruby, and distributed systems.",
     "https://razorpay.com/jobs/", "₹50K-75K/month"),

    ("Zomato", "Product Design Intern", "Gurgaon, India", "internship",
     "Design intuitive food delivery experiences for 100M+ users. Work closely with product and engineering teams.",
     "https://www.zomato.com/careers", "₹30K-50K/month"),

    ("Swiggy", "Data Science Intern", "Bangalore, India", "internship",
     "Build ML models for delivery time prediction, demand forecasting, and recommendation systems.",
     "https://careers.swiggy.com/", "₹40K-60K/month"),

    ("CRED", "Full Stack Intern", "Bangalore, India", "internship",
     "Build premium fintech experiences for CRED's 10M+ members. React Native, Node.js, and Kotlin.",
     "https://careers.cred.club/", "₹50K-80K/month"),

    ("Meesho", "ML Engineering Intern", "Bangalore, India", "internship",
     "Work on social commerce AI — image recognition, NLP for product cataloging, and personalization engines.",
     "https://careers.meesho.com/", "₹35K-55K/month"),

    ("PhonePe", "Android Developer Intern", "Bangalore, India", "internship",
     "Build India's #1 digital payments app used by 500M+ users. Work with Kotlin, Jetpack Compose.",
     "https://www.phonepe.com/careers/", "₹45K-65K/month"),

    ("Zerodha", "Systems Engineering Intern", "Bangalore, India", "internship",
     "Work on India's largest stock trading platform. Golang, PostgreSQL, and real-time data systems.",
     "https://zerodha.com/careers/", "₹40K-60K/month"),

    ("Postman", "API Platform Intern", "Bangalore, India", "internship",
     "Help build the world's #1 API development platform. Work on Node.js, Electron, and cloud infrastructure.",
     "https://www.postman.com/company/careers/", "₹50K-70K/month"),

    ("Freshworks", "SRE Intern", "Chennai, India", "internship",
     "Maintain reliability of SaaS products serving 60K+ businesses. Work with Kubernetes, AWS, and monitoring tools.",
     "https://www.freshworks.com/company/careers/", "₹35K-50K/month"),

    # ── Indian Companies — Full-time ─────────────────────────
    ("Flipkart", "Senior Software Engineer", "Bangalore, India", "full-time",
     "Design and build scalable backend services for supply chain and logistics. Java, Spring Boot, Kafka.",
     "https://www.flipkartcareers.com/#!/joblist", "₹25-45 LPA"),

    ("Razorpay", "Product Manager", "Bangalore, India", "full-time",
     "Own the payments dashboard product. Define roadmaps, drive feature delivery, and analyze metrics.",
     "https://razorpay.com/jobs/", "₹30-50 LPA"),

    ("Zomato", "Senior Data Engineer", "Gurgaon, India", "full-time",
     "Build real-time data pipelines for order tracking, analytics, and ML feature stores. Spark, Kafka, Airflow.",
     "https://www.zomato.com/careers", "₹20-40 LPA"),

    ("Paytm", "DevOps Engineer", "Noida, India", "full-time",
     "Manage cloud infrastructure for India's largest fintech ecosystem. Kubernetes, Terraform, AWS.",
     "https://jobs.lever.co/paytm", "₹18-35 LPA"),

    ("Infosys", "Associate Software Engineer", "Pune, India", "full-time",
     "Join the digital transformation team. Work on enterprise Java, cloud migration, and microservices.",
     "https://www.infosys.com/careers/", "₹4-8 LPA"),

    ("TCS", "Systems Engineer", "Mumbai, India", "full-time",
     "Work on automation, cloud solutions, and enterprise applications for global clients.",
     "https://www.tcs.com/careers", "₹4-7 LPA"),

    ("Zoho", "Member Technical Staff", "Chennai, India", "full-time",
     "Build SaaS products used by 80M+ users worldwide. Full ownership from design to deployment.",
     "https://www.zoho.com/careers/", "₹8-15 LPA"),

    ("BrowserStack", "Senior QA Engineer", "Mumbai, India", "full-time",
     "Ensure quality of the world's leading testing infrastructure. Selenium, Appium, CI/CD.",
     "https://www.browserstack.com/careers", "₹15-30 LPA"),

    ("Hasura", "Developer Advocate", "Bangalore, India", "full-time",
     "Grow the Hasura developer community. Create tutorials, speak at conferences, and build demo apps.",
     "https://hasura.io/careers/", "₹20-35 LPA"),

    ("Groww", "Frontend Engineer", "Bangalore, India", "full-time",
     "Build the investment platform for 40M+ Indians. React, TypeScript, and mobile-first design.",
     "https://groww.in/careers", "₹18-35 LPA"),

    # ── Global Companies — Internships ───────────────────────
    ("Google", "Software Engineering Intern", "Mountain View, USA", "internship",
     "Work on Google-scale infrastructure, search, or cloud products. C++, Java, Python.",
     "https://www.google.com/about/careers/applications/", "$8K-10K/month"),

    ("Microsoft", "Explore Intern", "Redmond, USA", "internship",
     "Rotational internship across PM, Design, and SWE. Build real features for Microsoft products.",
     "https://careers.microsoft.com/", "$7K-9K/month"),

    ("Meta", "ML Engineering Intern", "Menlo Park, USA", "internship",
     "Work on recommendation systems, NLP, or computer vision powering Instagram, WhatsApp, or Facebook.",
     "https://www.metacareers.com/", "$8K-10K/month"),

    ("Amazon", "SDE Intern", "Seattle, USA", "internship",
     "Build features for AWS, Alexa, or Retail. Java, distributed systems at massive scale.",
     "https://www.amazon.jobs/", "$8K-10K/month"),

    ("OpenAI", "Research Intern", "San Francisco, USA", "internship",
     "Contribute to frontier AI research. Work on language models, alignment, or safety.",
     "https://openai.com/careers/", "$10K-12K/month"),

    ("Stripe", "Software Engineering Intern", "San Francisco, USA", "internship",
     "Build the economic infrastructure of the internet. Ruby, Scala, distributed payments.",
     "https://stripe.com/jobs", "$9K-11K/month"),

    ("NVIDIA", "Deep Learning Intern", "Santa Clara, USA", "internship",
     "Work on GPU-accelerated computing, CUDA, or autonomous driving AI.",
     "https://www.nvidia.com/en-us/about-nvidia/careers/", "$7K-9K/month"),

    # ── Global Companies — Full-time ─────────────────────────
    ("Google", "Senior Software Engineer", "Bangalore, India", "full-time",
     "Work on Search, Cloud, or YouTube infrastructure from Google's India office.",
     "https://www.google.com/about/careers/applications/", "₹40-70 LPA"),

    ("Microsoft", "Software Engineer II", "Hyderabad, India", "full-time",
     "Build Azure cloud services and developer tools from Microsoft India Development Center.",
     "https://careers.microsoft.com/", "₹25-50 LPA"),

    ("Amazon", "SDE II", "Bangalore, India", "full-time",
     "Work on AWS services, retail platform, or Alexa from Amazon's India tech hub.",
     "https://www.amazon.jobs/", "₹30-55 LPA"),

    ("Adobe", "Computer Scientist", "Noida, India", "full-time",
     "Build creative and document cloud products. AI/ML for image/video processing.",
     "https://careers.adobe.com/", "₹25-45 LPA"),

    ("Salesforce", "Lead Software Engineer", "Hyderabad, India", "full-time",
     "Design enterprise SaaS platform components. Java, Kubernetes, and cloud-native architecture.",
     "https://careers.salesforce.com/", "₹30-50 LPA"),

    # ── Remote/Contract ──────────────────────────────────────
    ("Vercel", "Frontend Engineer", "Remote", "full-time",
     "Build the future of frontend development. Next.js, React, and edge computing.",
     "https://vercel.com/careers", "$120K-180K/year"),

    ("Supabase", "Backend Engineer", "Remote", "full-time",
     "Build the open-source Firebase alternative. PostgreSQL, Elixir, and TypeScript.",
     "https://supabase.com/careers", "$130K-170K/year"),

    ("PostHog", "Product Engineer", "Remote", "full-time",
     "Build open-source product analytics. React, Django, ClickHouse, and Kubernetes.",
     "https://posthog.com/careers", "$120K-170K/year"),

    ("Linear", "Senior Backend Engineer", "Remote", "full-time",
     "Build the issue tracking tool developers love. TypeScript, PostgreSQL, and real-time sync.",
     "https://linear.app/careers", "$140K-200K/year"),

    ("Grafana Labs", "Software Engineer — Observability", "Remote", "full-time",
     "Build open-source monitoring tools. Go, React, and distributed systems.",
     "https://grafana.com/about/careers/", "$130K-180K/year"),
]


async def seed_jobs() -> int:
    """Seed sample job listings if the jobs table is empty."""
    async with get_session() as session:
        count = (await session.execute(select(sqla_func.count(Job.id)))).scalar() or 0
        if count > 0:
            logger.info("Jobs table already has %d rows — skipping seed.", count)
            return count

        # Build company name → id mapping
        from database.models import Company
        result = await session.execute(select(Company))
        companies = {c.company_name: c.id for c in result.scalars().all()}

        added = 0
        for company_name, title, location, job_type, description, application_url, salary_range in _SEED_JOBS:
            company_id = companies.get(company_name)
            if not company_id:
                logger.debug("Skipping job for unknown company: %s", company_name)
                continue

            session.add(Job(
                company_id=company_id,
                title=title,
                location=location,
                job_type=job_type,
                description=description,
                url=application_url,
                application_url=application_url,
                salary_range=salary_range,
                source="seed",
                is_active=True,
            ))
            added += 1

    logger.info("Seeded %d sample job listings.", added)
    return added

"""SQLAlchemy ORM models for the job intelligence system."""

from __future__ import annotations

import datetime
from enum import IntEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""


# ──────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────


class Tier(IntEnum):
    """Monitoring tier — determines check frequency."""
    TIER1 = 1  # Top 5k   → every 30 min
    TIER2 = 2  # 20k      → every 3 hr
    TIER3 = 3  # 25k      → every 12 hr


# ──────────────────────────────────────────────────────────────
# Company
# ──────────────────────────────────────────────────────────────


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    website: Mapped[str | None] = mapped_column(String(1024))
    careers_url: Mapped[str | None] = mapped_column(String(1024))
    github_org: Mapped[str | None] = mapped_column(String(256))
    twitter_handle: Mapped[str | None] = mapped_column(String(256))
    country: Mapped[str] = mapped_column(String(128), default="Global", index=True)
    tier: Mapped[int] = mapped_column(Integer, default=Tier.TIER3, index=True)
    last_checked: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    internship_probability: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    last_signal_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    signals: Mapped[list[Signal]] = relationship(back_populates="company", cascade="all, delete-orphan")
    jobs: Mapped[list[Job]] = relationship(back_populates="company", cascade="all, delete-orphan")
    alerts: Mapped[list[Alert]] = relationship(back_populates="company", cascade="all, delete-orphan")
    hiring_history: Mapped[list[HiringHistory]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


# ──────────────────────────────────────────────────────────────
# Signal
# ──────────────────────────────────────────────────────────────


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(64), index=True)  # career | github | funding | social
    raw_data: Mapped[str | None] = mapped_column(Text)
    processed_result: Mapped[str | None] = mapped_column(Text)  # JSON string
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    internship_related: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship(back_populates="signals")


# ──────────────────────────────────────────────────────────────
# Job
# ──────────────────────────────────────────────────────────────


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(256), index=True)
    job_type: Mapped[str | None] = mapped_column(String(64), index=True)  # internship | full-time | contract | part-time
    application_url: Mapped[str | None] = mapped_column(String(1024))
    salary_range: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str | None] = mapped_column(String(128))  # careers_page | github | api | seed
    detected_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship(back_populates="jobs")


# ──────────────────────────────────────────────────────────────
# Alert
# ──────────────────────────────────────────────────────────────


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    probability: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship(back_populates="alerts")


# ──────────────────────────────────────────────────────────────
# Hiring History (for historical prediction)
# ──────────────────────────────────────────────────────────────


class HiringHistory(Base):
    __tablename__ = "hiring_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    role: Mapped[str] = mapped_column(String(512))
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)

    company: Mapped[Company] = relationship(back_populates="hiring_history")

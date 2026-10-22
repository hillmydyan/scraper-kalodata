"""
SQLAlchemy 2.0 models for Kalodata Scraper & Dashboard.
Corresponds to PRD §11 data model definitions.
"""

import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String, Integer, Float, Numeric, Boolean, DateTime, Date,
    ForeignKey, UniqueConstraint, Index, Text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)  # 'admin' | 'user'
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Flask-Login compatibility
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)


class AccountProfile(Base):
    __tablename__ = "account_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(50), default="kalodata", nullable=False)
    account_label: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    country_scope: Mapped[List[str]] = mapped_column(JSON, default=lambda: ["ID", "MY", "TH"])
    profile_dir_name: Mapped[str] = mapped_column(String(100), nullable=False)
    ui_language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    session_status: Mapped[str] = mapped_column(
        String(30), default="WAITING_FOR_VERIFICATION", nullable=False
    )  # READY, LOGIN_REQUIRED, WAITING_FOR_VERIFICATION, VALIDATING, DISABLED, ERROR
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_account_change_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    account_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    account_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trigger: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)  # scheduled | manual
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="RUNNING", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    jobs = relationship("ScrapeJob", back_populates="run", cascade="all, delete-orphan")


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("scrape_runs.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="kalodata", nullable=False)
    module: Mapped[str] = mapped_column(String(50), default="product", nullable=False)
    country_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    account_profile_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("account_profiles.id"), nullable=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False, index=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(String(50), default="INIT", nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_found: Mapped[int] = mapped_column(Integer, default=0)
    rows_saved: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    resumed_from_job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    checkpoint: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    run = relationship("ScrapeRun", back_populates="jobs")
    results = relationship("KalodataProductResult", back_populates="job", cascade="all, delete-orphan")
    creator_results = relationship("KalodataCreatorProductResult", back_populates="job", cascade="all, delete-orphan")
    rejected_rows = relationship("ScrapeJobRowsRejected", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_job_country_period_status", "country_code", "period_start", "status"),
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    kalodata_product_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str] = mapped_column(String(10), nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    shop_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    product_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("country_code", "source_product_id", name="uq_product_country_source_id"),
    )


class KalodataProductResult(Base):
    __tablename__ = "kalodata_product_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scrape_job_id: Mapped[str] = mapped_column(String(36), ForeignKey("scrape_jobs.id"), nullable=False)
    product_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("products.id"), nullable=True)
    source_product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    shop_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    product_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    revenue_value: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    revenue_raw: Mapped[str] = mapped_column(String(100), nullable=False)
    revenue_is_abbreviated: Mapped[bool] = mapped_column(Boolean, default=False)
    sales_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sales_raw: Mapped[str] = mapped_column(String(100), nullable=False)
    commission_rate: Mapped[Optional[float]] = mapped_column(Numeric(6, 4), nullable=True)
    commission_raw: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(10), nullable=False)
    video_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_url_type: Mapped[Optional[str]] = mapped_column(String(20), default="tiktok")  # tiktok | kalodata
    video_selection_method: Mapped[str] = mapped_column(String(50), default="top_revenue")
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    job = relationship("ScrapeJob", back_populates="results")

    __table_args__ = (
        UniqueConstraint(
            "country_code", "source_product_id", "period_start", "period_end",
            name="uq_product_result_unique_period"
        ),
        Index("idx_result_country_period", "country_code", "period_start"),
    )


class KalodataCreatorProductResult(Base):
    __tablename__ = "kalodata_creator_product_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scrape_job_id: Mapped[str] = mapped_column(String(36), ForeignKey("scrape_jobs.id"), nullable=False)
    creator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    creator_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    creator_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    product_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    shop_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    product_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    revenue_value: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    revenue_raw: Mapped[str] = mapped_column(String(100), nullable=False)
    sales_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sales_raw: Mapped[str] = mapped_column(String(100), nullable=False)
    commission_rate: Mapped[Optional[float]] = mapped_column(Numeric(6, 4), nullable=True)
    commission_raw: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(10), nullable=False)
    country_code: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    job = relationship("ScrapeJob", back_populates="creator_results")

    __table_args__ = (
        Index("idx_creator_result_country_period", "country_code", "period_start"),
    )



class ScrapeJobRowsRejected(Base):
    __tablename__ = "scrape_job_rows_rejected"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scrape_job_id: Mapped[str] = mapped_column(String(36), ForeignKey("scrape_jobs.id"), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    raw: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    job = relationship("ScrapeJob", back_populates="rejected_rows")


class ExportFile(Base):
    __tablename__ = "export_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scrape_job_id: Mapped[str] = mapped_column(String(36), ForeignKey("scrape_jobs.id"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(10), nullable=False)
    module: Mapped[str] = mapped_column(String(50), default="product", nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="SUCCESS")  # SUCCESS | FAILED | EMPTY
    version: Mapped[int] = mapped_column(Integer, default=1)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class DiagnosticScreenshot(Base):
    __tablename__ = "diagnostic_screenshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scrape_job_id: Mapped[str] = mapped_column(String(36), ForeignKey("scrape_jobs.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

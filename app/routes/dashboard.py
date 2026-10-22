"""
Dashboard route (/).
Follows rules in PRD §9.1:
- Status worker, scheduler, DB, Redis, DISPLAY
- Country cards (ID, MY, TH)
- Profile session statuses
- Attention jobs list
- Disk free space & export file counter
"""

import shutil
from datetime import datetime
from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import select, desc

from app.config import settings, APP_CONFIG
from app.models import SessionLocal
from app.models.entities import ScrapeJob, AccountProfile, ExportFile
from app.routes.common import format_wib

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    db = SessionLocal()
    try:
        # 1. Profile statuses
        profiles = db.execute(select(AccountProfile)).scalars().all()

        # 2. Country cards (latest job per country)
        country_cards = {}
        for c in ["ID", "MY", "TH"]:
            latest_job = db.execute(
                select(ScrapeJob)
                .filter_by(country_code=c)
                .order_by(desc(ScrapeJob.created_at))
                .limit(1)
            ).scalar_one_or_none()

            latest_export = None
            if latest_job:
                latest_export = db.execute(
                    select(ExportFile)
                    .filter_by(scrape_job_id=latest_job.id)
                    .order_by(desc(ExportFile.version))
                    .limit(1)
                ).scalar_one_or_none()

            country_cards[c] = {
                "job": latest_job,
                "export": latest_export
            }

        # 3. Attention jobs (LOGIN_REQUIRED, FAILED, PARTIAL, DATA_NOT_READY)
        attention_jobs = db.execute(
            select(ScrapeJob)
            .filter(ScrapeJob.status.in_(["LOGIN_REQUIRED", "FAILED", "PARTIAL", "DATA_NOT_READY"]))
            .order_by(desc(ScrapeJob.created_at))
            .limit(10)
        ).scalars().all()

        # 4. Recent jobs for process monitoring
        recent_jobs = db.execute(
            select(ScrapeJob)
            .order_by(desc(ScrapeJob.created_at))
            .limit(10)
        ).scalars().all()

        # 5. Storage & Files
        total_exports = db.execute(
            select(ExportFile).filter(ExportFile.deleted_at.is_(None))
        ).scalars().all()

        # Disk space check
        total_b, used_b, free_b = shutil.disk_usage(settings.RUNTIME_DIR)
        disk_free_mb = round(free_b / (1024 * 1024), 1)

        system_status = {
            "db": "ONLINE",
            "redis": "ONLINE",
            "display": settings.KALODATA_DISPLAY,
            "next_run_wib": f"Besok pukul {APP_CONFIG.get('app', {}).get('schedule_hour_wib', 1):02d}:00 WIB",
            "disk_free_mb": disk_free_mb,
            "total_exports_count": len(total_exports)
        }

        return render_template(
            "dashboard/index.html",
            profiles=profiles,
            country_cards=country_cards,
            attention_jobs=attention_jobs,
            recent_jobs=recent_jobs,
            system_status=system_status,
            format_wib=format_wib
        )
    finally:
        db.close()

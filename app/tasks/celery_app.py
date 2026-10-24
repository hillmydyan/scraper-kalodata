"""
Celery configuration and background tasks for Kalodata Scraper.
Follows rules in PRD §8.1, §8.2, and §13.2.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from celery import Celery
from celery.schedules import crontab
import structlog

from app.config import settings, APP_CONFIG
from app.models import SessionLocal
from app.models.entities import ScrapeRun, ScrapeJob
from app.services.job_service import JobService
from app.services.export_service import ExportService
from app.services.session_service import SessionService
from app.services.retention_service import RetentionService

logger = structlog.get_logger(__name__)

celery_app = Celery(
    "kalodata_scraper",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    timezone=settings.TZ,
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_time_limit=settings.DAILY_RUN_TIMEOUT_MINUTES * 60,
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
)

# Scheduled tasks (Celery Beat) (§8.1, §8.2)
celery_app.conf.beat_schedule = {
    "daily-kalodata-run": {
        "task": "app.tasks.celery_app.run_daily_pipeline",
        "schedule": crontab(hour=APP_CONFIG.get("app", {}).get("schedule_hour_wib", 1), minute=0),
    },
    "check-custom-schedule": {
        "task": "app.tasks.celery_app.check_and_run_scheduled_pipeline",
        "schedule": crontab(minute="*"),
    },
    "daily-retention-cleanup": {
        "task": "app.tasks.celery_app.run_cleanup",
        "schedule": crontab(hour=3, minute=0),
    },
    "periodic-session-check": {
        "task": "app.tasks.celery_app.check_session",
        "schedule": crontab(hour="*/6", minute=0),
    }
}


@celery_app.task(name="app.tasks.celery_app.check_and_run_scheduled_pipeline")
def check_and_run_scheduled_pipeline():
    """
    Checks every minute if custom configured schedule matches current WIB time.
    """
    import zoneinfo
    wib_tz = zoneinfo.ZoneInfo("Asia/Jakarta")
    now_wib = datetime.now(wib_tz)
    current_time_str = now_wib.strftime("%H:%M")

    db = SessionLocal()
    try:
        from app.models.entities import Setting, ScrapeRun
        setting = db.get(Setting, "schedule_config")
        if not setting or not isinstance(setting.value, dict):
            return "No custom schedule configured"

        cfg = setting.value
        if not cfg.get("auto_schedule", True):
            return "Auto schedule disabled"

        raw_time = str(cfg.get("time", "")).replace("WIB", "").strip()
        target_time_str = None
        for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
            try:
                t = datetime.strptime(raw_time, fmt).time()
                target_time_str = t.strftime("%H:%M")
                break
            except ValueError:
                pass

        if not target_time_str or target_time_str != current_time_str:
            return f"Time mismatch: current {current_time_str} != target {target_time_str}"

        # Check if already ran today for scheduled trigger
        today = now_wib.date()
        already_ran = db.query(ScrapeRun).filter(
            ScrapeRun.trigger == "scheduled",
            ScrapeRun.period_start == today - timedelta(days=1)
        ).first()

        if already_ran:
            return "Already executed today"

        logger.info("Executing scheduled pipeline for custom time", target_time=target_time_str)
        return run_daily_pipeline()
    finally:
        db.close()


@celery_app.task(name="app.tasks.celery_app.run_daily_pipeline")
def run_daily_pipeline():
    """
    Orchestrates daily pipeline in exact sequence (§8.2):
    1. Healthcheck
    2. Session validation
    3. Serial scrape ID -> MY -> TH
    4. Export Excel per country
    5. Finalize run
    """
    logger.info("Starting scheduled daily Kalodata pipeline")
    db = SessionLocal()
    try:
        # 1. Healthcheck & Session check
        profile = SessionService.get_or_create_default_profile(db)
        val_res = SessionService.validate_profile_session(db, profile.id)
        if val_res.get("status") != "READY":
            logger.warning("Session not READY, pipeline aborted", status=val_res.get("status"))
            return {"error": "SESSION_NOT_READY", "details": val_res}

        # 2. Create ScrapeRun
        yesterday = date.today() - timedelta(days=1)
        run = JobService.create_daily_run(db, period_date=yesterday, trigger="scheduled", created_by="celery_beat")

        # 3. Serial scrape per country
        countries = ["ID", "MY", "TH"]
        for c in countries:
            logger.info("Dispatching scrape for country", country=c, run_id=run.id)
            # Find job
            job = db.query(ScrapeJob).filter_by(run_id=run.id, country_code=c).first()
            if job:
                # Scrape synchronously in worker
                scrape_country_job(job.id)

        # 4. Finalize run
        run.status = "COMPLETED"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Daily pipeline completed successfully", run_id=run.id)
        return {"run_id": run.id, "status": "COMPLETED"}
    finally:
        db.close()


@celery_app.task(name="app.tasks.celery_app.scrape_country_job")
def scrape_country_job(job_id: str, limit: int = 2000, headless: Optional[bool] = None):
    """Executes single country scrape job."""
    from app.services.job_service import JobService
    if headless is None:
        headless = settings.KALODATA_HEADLESS
    JobService.execute_job_now(job_id, limit=limit, headless=headless)
    return {"job_id": job_id, "status": "FINISHED"}


@celery_app.task(name="app.tasks.celery_app.open_login_browser")
def open_login_browser(profile_label: str, profile_id: str, email: Optional[str] = None, password: Optional[str] = None):
    """Launches manual login browser in worker container where VNC is running."""
    from app.scrapers.kalodata.session import SessionManager
    from app.models.entities import AccountProfile, ScrapeJob
    from app.services.job_service import JobService
    try:
        success, msg = SessionManager.launch_manual_login(
            profile_label=profile_label,
            poll_duration_min=15,
            email=email,
            password=password
        )
        db = SessionLocal()
        try:
            p = db.get(AccountProfile, profile_id)
            if p:
                p.session_status = "READY" if success else "LOGIN_REQUIRED"
                if success:
                    p.last_validated_at = datetime.now(timezone.utc)
                db.commit()

            # If login succeeded, automatically resume pending jobs waiting for login
            if success:
                pending_jobs = db.query(ScrapeJob).filter(
                    ScrapeJob.status == "PENDING",
                    ScrapeJob.stage == "WAITING_LOGIN"
                ).all()
                for pj in pending_jobs:
                    logger.info("Auto-resuming pending job after manual login", job_id=pj.id)
                    JobService.dispatch_run_in_background(pj.run_id or pj.id, limit=200, headless=True)
        finally:
            db.close()
        return {"status": "SUCCESS" if success else "FAILED", "message": msg}
    except Exception as e:
        logger.error("Failed manual login browser task", error=str(e))
        return {"status": "ERROR", "message": str(e)}


@celery_app.task(name="app.tasks.celery_app.run_cleanup")
def run_cleanup():
    db = SessionLocal()
    try:
        return RetentionService.cleanup_old_data(db)
    finally:
        db.close()


@celery_app.task(name="app.tasks.celery_app.check_session")
def check_session():
    db = SessionLocal()
    try:
        profile = SessionService.get_or_create_default_profile(db)
        return SessionService.validate_profile_session(db, profile.id)
    finally:
        db.close()

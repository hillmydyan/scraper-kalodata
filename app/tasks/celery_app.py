"""
Celery configuration and background tasks for Kalodata Scraper.
Follows rules in PRD §8.1, §8.2, and §13.2.
"""

from datetime import date, datetime, timedelta, timezone
from celery import Celery
from celery.schedules import crontab
import structlog

from app.config import settings
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
        "schedule": crontab(hour=settings.APP_CONFIG.get("app", {}).get("schedule_hour_wib", 1), minute=0),
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
def scrape_country_job(job_id: str):
    """Executes single country scrape job."""
    from app.scrapers.base import BaseScraper
    from app.scrapers.kalodata.navigation import KalodataNavigator
    from app.scrapers.kalodata.product_list import ProductListScraper

    db = SessionLocal()
    job = db.get(ScrapeJob, job_id)
    if not job:
        return {"error": "Job not found"}

    job.status = "RUNNING"
    job.started_at = datetime.now(timezone.utc)
    db.commit()

    profile_label = "indo"
    if job.account_profile_id:
        from app.models.entities import AccountProfile
        acc_p = db.get(AccountProfile, job.account_profile_id)
        if acc_p and acc_p.profile_dir_name:
            profile_label = acc_p.profile_dir_name

    scraper = BaseScraper(profile_label=profile_label)
    try:
        scraper.acquire_lock()
        context = scraper.launch_browser(headless=True)
        page = context.new_page()

        nav = KalodataNavigator(page)
        nav.ensure_ui_language(settings.KALODATA_UI_LANGUAGE)

        if getattr(job, "module", "product") == "creator":
            from app.scrapers.kalodata.creator_scraper import CreatorScraper

            page.goto(f"{settings.KALODATA_BASE_URL.rstrip('/')}/creator", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            nav.switch_and_verify_region(job.country_code)

            creator_scraper = CreatorScraper(page, job.country_code)
            creator_scraper.apply_filters()

            min_rev = getattr(settings, "MIN_CREATOR_REVENUE_IDR", 4000000.0)
            scrape_res = creator_scraper.scrape_creators(
                max_creators=None,
                min_revenue=min_rev,
                products_per_creator=3,
                period_date=job.period_start
            )

            items = scrape_res["items"]
            JobService.upsert_creator_results(db, job.id, job.country_code, job.period_start, items)
            job.rows_duplicate = 0
            job.rows_found = scrape_res["total_creators"]
            job.rows_saved = len(items)
            job.rows_rejected = 0

            final_status = "SUCCESS" if items else "NO_DATA"
            JobService.finalize_job(
                db, job.id,
                status=final_status,
                meta_updates={"revenue_source_method": "creator_filter"}
            )

            # Trigger Excel export
            ExportService.export_job_results(db, job.id)
            return {"job_id": job.id, "status": final_status, "saved": len(items)}
        else:
            nav.switch_and_verify_region(job.country_code)
            nav.apply_date_range(job.period_start, job.period_end)
            nav.apply_category_filter(job.country_code)
            rev_method = nav.apply_revenue_source_filter()

            list_scraper = ProductListScraper(page, job.country_code)
            min_sales = getattr(settings, "MIN_PRODUCT_SALES", 50)
            res = list_scraper.scrape_products(
                max_limit=settings.MAX_PRODUCTS_PER_COUNTRY,
                min_sales=min_sales,
                revenue_source_method=rev_method
            )

            items = res["items"]
            rejected = res["rejected"]

            if rejected:
                JobService.record_rejected_rows(db, job.id, rejected)

            dups = JobService.upsert_product_results(db, job.id, job.country_code, job.period_start, items)
            job.rows_duplicate = dups
            job.rows_found = res["total_scanned"]
            job.rows_saved = len(items)
            job.rows_rejected = len(rejected)

            final_status = "SUCCESS" if items else "NO_DATA"
            if res["is_truncated"]:
                final_status = "PARTIAL"

            JobService.finalize_job(
                db, job.id,
                status=final_status,
                meta_updates={"revenue_source_method": rev_method}
            )

            # Trigger Excel export
            ExportService.export_job_results(db, job.id)
            return {"job_id": job.id, "status": final_status, "saved": len(items)}
    except Exception as e:
        logger.error("Job failed with error", job_id=job_id, error=str(e))
        JobService.finalize_job(db, job.id, status="FAILED", error_code="UNKNOWN", error_summary=str(e))
        return {"job_id": job.id, "status": "FAILED", "error": str(e)}
    finally:
        scraper.close_browser()
        scraper.release_lock()
        db.close()


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

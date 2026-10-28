"""
Background Auto-Scheduler Service.
Enables scheduled daily execution of Kalodata scrapers (Creator or Product)
at the configured time (WIB), running seamlessly both in standalone Flask (dev server)
and Celery Beat.
"""

import threading
import time
import zoneinfo
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List
import structlog

from app.config import settings
from app.models import SessionLocal

logger = structlog.get_logger(__name__)


def parse_schedule_time(raw_time: str) -> Optional[str]:
    """
    Parses user input time string into normalized '%H:%M' 24-hour string.
    Supports: '12:00 PM', '12:00', '12.00', '12:00 WIB', '12.00 WIB', '01:10 AM', '14:30', '12'.
    """
    cleaned = str(raw_time).upper().replace("WIB", "").strip()
    cleaned = cleaned.replace(".", ":")
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p", "%H:%M:%S", "%I:%M"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%H:%M")
        except ValueError:
            pass

    if cleaned.isdigit() and 0 <= int(cleaned) <= 23:
        return f"{int(cleaned):02d}:00"
    return None


class SchedulerService:
    _lock = threading.Lock()
    _last_triggered_minute: Optional[str] = None
    _thread: Optional[threading.Thread] = None
    _stop_event = threading.Event()

    @classmethod
    def check_and_trigger(cls) -> Optional[str]:
        """
        Evaluates schedule_config in DB against current WIB time.
        If time matches and auto_schedule is True, dispatches the run.
        """
        wib_tz = zoneinfo.ZoneInfo("Asia/Jakarta")
        now_wib = datetime.now(wib_tz)
        current_time_str = now_wib.strftime("%H:%M")
        minute_key = now_wib.strftime("%Y-%m-%d %H:%M")

        with cls._lock:
            if cls._last_triggered_minute == minute_key:
                return "Already triggered this minute"

        db = SessionLocal()
        try:
            from app.models.entities import Setting, ScrapeRun, ScrapeJob
            setting = db.get(Setting, "schedule_config")
            if not setting or not isinstance(setting.value, dict):
                return "No schedule_config found"

            cfg = setting.value
            if not cfg.get("auto_schedule", False):
                return "Auto schedule disabled"

            raw_time = cfg.get("time", "")
            target_time_str = parse_schedule_time(raw_time)
            if not target_time_str:
                return f"Invalid time format in schedule_config: {raw_time}"

            if current_time_str != target_time_str:
                return f"Time mismatch: current {current_time_str} != target {target_time_str}"

            # Auto-cleanup stale runs older than timeout (default 120 mins)
            stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=getattr(settings, "DAILY_RUN_TIMEOUT_MINUTES", 120))
            stale_runs = db.query(ScrapeRun).filter(
                ScrapeRun.status == "RUNNING",
                ScrapeRun.started_at < stale_cutoff
            ).all()
            for sr in stale_runs:
                sr.status = "CANCELLED"
                sr.finished_at = datetime.now(timezone.utc)
                logger.info("Auto-cancelled stale scrape run", run_id=sr.id, started_at=sr.started_at)
            if stale_runs:
                db.commit()

            # Ensure no active scrape job is currently executing to avoid profile lock collision
            active_job = db.query(ScrapeJob).filter(ScrapeJob.status.in_(["RUNNING", "CLAIMED", "IN_PROGRESS"])).first()
            if active_job:
                logger.info("A scrape job is currently executing, skipping scheduled trigger", job_id=active_job.id)
                return "A scrape job is currently executing"

            # Check if there is a recently started run (< 2h) that still has active/pending jobs
            recent_run = db.query(ScrapeRun).filter(
                ScrapeRun.status == "RUNNING",
                ScrapeRun.started_at >= stale_cutoff
            ).first()
            if recent_run:
                pending_count = db.query(ScrapeJob).filter(
                    ScrapeJob.run_id == recent_run.id,
                    ScrapeJob.status.in_(["PENDING", "RUNNING", "CLAIMED", "IN_PROGRESS"])
                ).count()
                if pending_count > 0:
                    logger.info("A scrape run is still active with pending jobs, skipping trigger", run_id=recent_run.id, pending=pending_count)
                    return "A scrape run is already in progress"
                else:
                    recent_run.status = "COMPLETED"
                    recent_run.finished_at = datetime.now(timezone.utc)
                    db.commit()

            with cls._lock:
                cls._last_triggered_minute = minute_key

            yesterday = (now_wib - timedelta(days=1)).date()
            region = cfg.get("target_region", "ALL")
            target_countries = None if region == "ALL" else [region]
            module = cfg.get("module", "creator")
            headless = getattr(settings, "KALODATA_HEADLESS", False)

            from app.services.job_service import JobService
            if module == "both":
                def run_both_sequentially():
                    logger.info("Auto-scheduler starting sequential runs (creator then product)")
                    for mod in ["creator", "product"]:
                        run_id = None
                        db_init = SessionLocal()
                        try:
                            min_s = JobService.get_min_product_sales(db_init) if mod == "product" else None
                            max_s = JobService.get_max_product_sales(db_init) if mod == "product" else None
                            run = JobService.create_daily_run(
                                db_init,
                                period_date=yesterday,
                                trigger="scheduled",
                                created_by="auto_scheduler",
                                countries=target_countries,
                                module=mod,
                                min_sales=min_s,
                                max_sales=max_s
                            )
                            db_init.commit()
                            run_id = run.id
                        finally:
                            db_init.close()

                        # Execute jobs synchronously in this background thread
                        db_exec = SessionLocal()
                        try:
                            jobs = db_exec.query(ScrapeJob).filter_by(run_id=run_id).order_by(ScrapeJob.created_at).all()
                            for j in jobs:
                                JobService.execute_job_now(j.id, limit=None, headless=headless)
                            r_obj = db_exec.get(ScrapeRun, run_id)
                            if r_obj:
                                r_obj.status = "COMPLETED"
                                r_obj.finished_at = datetime.now(timezone.utc)
                                db_exec.commit()
                        except Exception as ex:
                            logger.error("Error executing scheduled run for module", module=mod, error=str(ex))
                            try:
                                r_obj = db_exec.get(ScrapeRun, run_id)
                                if r_obj:
                                    r_obj.status = "FAILED"
                                    r_obj.finished_at = datetime.now(timezone.utc)
                                    db_exec.commit()
                            except Exception:
                                pass
                        finally:
                            db_exec.close()

                threading.Thread(target=run_both_sequentially, daemon=True, name="SequentialScheduledRuns").start()
                return "Started sequential scheduled runs for creator and product"
            else:
                min_s = JobService.get_min_product_sales(db) if module == "product" else None
                max_s = JobService.get_max_product_sales(db) if module == "product" else None
                run = JobService.create_daily_run(
                    db,
                    period_date=yesterday,
                    trigger="scheduled",
                    created_by="auto_scheduler",
                    countries=target_countries,
                    module=module,
                    min_sales=min_s,
                    max_sales=max_s
                )
                db.commit()

                logger.info(
                    "Auto schedule triggered successfully!",
                    run_id=run.id,
                    module=module,
                    region=region,
                    time=target_time_str
                )

                # Limit is None for scheduled runs to scrape all valid rows matching thresholds
                JobService.dispatch_run_in_background(run.id, limit=None, headless=headless)
                return f"Triggered scheduled run: {run.id}"
        except Exception as e:
            logger.error("Error evaluating auto-schedule", error=str(e), exc_info=True)
            return f"Error: {e}"
        finally:
            db.close()

    @classmethod
    def start_scheduler_thread(cls):
        """Starts background monitoring loop for standalone development server."""
        with cls._lock:
            if cls._thread and cls._thread.is_alive():
                return
            cls._stop_event.clear()
            cls._thread = threading.Thread(target=cls._run_loop, daemon=True, name="AutoSchedulerThread")
            cls._thread.start()
            logger.info("AutoScheduler background thread started")

    @classmethod
    def stop_scheduler_thread(cls):
        """Stops background loop."""
        cls._stop_event.set()

    @classmethod
    def _run_loop(cls):
        logger.info("AutoScheduler background loop running")
        while not cls._stop_event.is_set():
            try:
                cls.check_and_trigger()
            except Exception as e:
                logger.warning("Error in AutoScheduler loop", error=str(e))
            cls._stop_event.wait(15)

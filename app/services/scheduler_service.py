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
            from app.models.entities import Setting, ScrapeRun
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

            # Ensure no run is currently executing to avoid profile lock collision
            running_run = db.query(ScrapeRun).filter(ScrapeRun.status == "RUNNING").first()
            if running_run:
                logger.info("A scrape run is already in progress, skipping scheduled trigger", run_id=running_run.id)
                return "A scrape run is already in progress"

            with cls._lock:
                cls._last_triggered_minute = minute_key

            yesterday = (now_wib - timedelta(days=1)).date()
            region = cfg.get("target_region", "ALL")
            target_countries = None if region == "ALL" else [region]
            modules_to_run = ["creator", "product"] if module == "both" else [module]
            triggered_runs = []

            from app.services.job_service import JobService
            for mod in modules_to_run:
                run = JobService.create_daily_run(
                    db,
                    period_date=yesterday,
                    trigger="scheduled",
                    created_by="auto_scheduler",
                    countries=target_countries,
                    module=mod
                )
                db.commit()

                logger.info(
                    "Auto schedule triggered successfully!",
                    run_id=run.id,
                    module=mod,
                    region=region,
                    time=target_time_str
                )

                # Limit is None for scheduled runs to scrape all valid rows matching thresholds
                JobService.dispatch_run_in_background(run.id, limit=None, headless=headless)
                triggered_runs.append(run.id)

            return f"Triggered scheduled run(s): {', '.join(triggered_runs)}"
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

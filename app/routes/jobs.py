"""
Jobs and Runs management routes (/jobs, /jobs/<id>).
Follows rules in PRD §8.6, §9.4, and §9.5.
"""

from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from sqlalchemy import select, desc

from app.models import SessionLocal
from app.models.entities import ScrapeJob, ScrapeRun, DiagnosticScreenshot, AuditLog, Setting
from app.routes.common import admin_required, format_wib
from app.services.job_service import JobService

jobs_bp = Blueprint("jobs", __name__)


from app.config import APP_CONFIG
import zoneinfo

WIB_TZ = zoneinfo.ZoneInfo("Asia/Jakarta")


@jobs_bp.route("/jobs")
@login_required
def index():
    db = SessionLocal()
    try:
        jobs = db.execute(
            select(ScrapeJob).order_by(desc(ScrapeJob.created_at)).limit(50)
        ).scalars().all()

        today_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        now_wib = datetime.now(WIB_TZ).strftime("%H:%M WIB")

        # Load saved schedule configuration from Setting table if available
        saved_setting = db.get(Setting, "schedule_config")
        if saved_setting and isinstance(saved_setting.value, dict):
            schedule_config = dict(saved_setting.value)
            schedule_config["current_time_wib"] = now_wib
        else:
            schedule_config = {
                "time": "12:00",
                "target_limit": 200,
                "target_region": "ALL",
                "module": "creator",
                "auto_schedule": True,
                "current_time_wib": now_wib
            }

        from app.services.scheduler_service import parse_schedule_time
        saved_24 = parse_schedule_time(schedule_config.get("time", "12:00")) or "12:00"
        parts = saved_24.split(":")
        schedule_config["selected_hour"] = parts[0] if len(parts) == 2 else "12"
        schedule_config["selected_minute"] = parts[1] if len(parts) == 2 else "00"
        schedule_config["time_24"] = saved_24

        # Load saved manual trigger configuration from Setting table if available
        saved_manual = db.get(Setting, "manual_config")
        if saved_manual and isinstance(saved_manual.value, dict):
            manual_config = dict(saved_manual.value)
        else:
            manual_config = {
                "limit": schedule_config.get("target_limit", 200),
                "module": "creator",
                "country": "ID",
                "headless": "true"
            }

        min_product_sales = JobService.get_min_product_sales(db)
        max_product_sales = JobService.get_max_product_sales(db)
        return render_template(
            "jobs/index.html",
            jobs=jobs,
            default_period=today_str,
            schedule_config=schedule_config,
            manual_config=manual_config,
            min_product_sales=min_product_sales,
            max_product_sales=max_product_sales,
            format_wib=format_wib
        )
    finally:
        db.close()


@jobs_bp.route("/jobs/save-schedule", methods=["POST"])
@admin_required
def save_schedule():
    schedule_hour = request.form.get("schedule_hour")
    schedule_minute = request.form.get("schedule_minute")
    if schedule_hour is not None and schedule_minute is not None:
        try:
            h_int = int(schedule_hour)
            m_int = int(schedule_minute)
            schedule_time = f"{h_int:02d}:{m_int:02d}"
        except ValueError:
            schedule_time = request.form.get("schedule_time", "12:00")
    else:
        schedule_time = request.form.get("schedule_time", "12:00")

    target_limit_str = request.form.get("target_limit", "400")
    target_region = request.form.get("target_region", "ALL")
    module = request.form.get("module", "creator")
    auto_schedule = request.form.get("auto_schedule") in ("on", "true", "1")

    try:
        target_limit = int(target_limit_str)
    except ValueError:
        target_limit = 400

    if module == "product" and target_limit > 400:
        target_limit = 400

    config_data = {
        "time": schedule_time,
        "target_limit": target_limit,
        "target_region": target_region,
        "module": module,
        "auto_schedule": auto_schedule,
    }

    db = SessionLocal()
    try:
        from sqlalchemy.orm.attributes import flag_modified
        setting = db.get(Setting, "schedule_config")
        if not setting:
            setting = Setting(key="schedule_config", value=config_data, updated_by=current_user.username)
            db.add(setting)
        else:
            setting.value = config_data
            setting.updated_by = current_user.username
            setting.updated_at = datetime.now(timezone.utc)
            flag_modified(setting, "value")

        db.commit()

        # Update min_product_sales and max_product_sales if provided
        min_sales_input = request.form.get("min_product_sales")
        if min_sales_input:
            try:
                min_sales_val = max(1, int(min_sales_input))
                st_sales = db.get(Setting, "min_product_sales")
                if not st_sales:
                    st_sales = Setting(key="min_product_sales", value=min_sales_val, updated_by=current_user.username)
                    db.add(st_sales)
                else:
                    st_sales.value = min_sales_val
                    st_sales.updated_by = current_user.username
                    st_sales.updated_at = datetime.now(timezone.utc)
                    flag_modified(st_sales, "value")
                db.commit()
            except (ValueError, TypeError):
                pass

        max_sales_input = request.form.get("max_product_sales")
        st_max = db.get(Setting, "max_product_sales")
        max_sales_val = None
        if max_sales_input and max_sales_input.strip():
            try:
                mv = int(max_sales_input)
                if mv > 0:
                    max_sales_val = mv
            except (ValueError, TypeError):
                pass
        if not st_max:
            st_max = Setting(key="max_product_sales", value=max_sales_val, updated_by=current_user.username)
            db.add(st_max)
        else:
            st_max.value = max_sales_val
            st_max.updated_by = current_user.username
            st_max.updated_at = datetime.now(timezone.utc)
            flag_modified(st_max, "value")
        db.commit()

        # Ensure scheduler thread is running and reset trigger cache
        from app.services.scheduler_service import SchedulerService
        SchedulerService.start_scheduler_thread()
        with SchedulerService._lock:
            SchedulerService._last_triggered_minute = None

        flash("Konfigurasi jadwal otomatis harian berhasil disimpan!", "success")
    finally:
        db.close()

    return redirect(url_for("jobs.index"))


@jobs_bp.route("/jobs/trigger", methods=["POST"])
@admin_required
def trigger_manual():
    country_input = request.form.get("country") or request.form.get("target_region", "ALL")
    if "ID" in country_input:
        country = "ID"
    elif "MY" in country_input:
        country = "MY"
    elif "TH" in country_input:
        country = "TH"
    else:
        country = "ALL"

    module = request.form.get("module", "product")
    if module not in ("product", "creator"):
        module = "product"

    limit_str = request.form.get("limit") or request.form.get("target_limit", "400")
    try:
        limit = int(limit_str)
    except ValueError:
        limit = 400

    if module == "product" and limit > 400:
        limit = 400

    period_str = request.form.get("period")
    headless_str = request.form.get("headless", "false")
    headless = (headless_str == "true")

    try:
        period_date = datetime.strptime(period_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        period_date = date.today() - timedelta(days=1)

    target_countries = None if country == "ALL" else [country]

    db = SessionLocal()
    try:
        min_sales_str = request.form.get("min_sales")
        try:
            min_sales = int(min_sales_str) if min_sales_str else JobService.get_min_product_sales(db)
        except (ValueError, TypeError):
            min_sales = JobService.get_min_product_sales(db)

        max_sales_str = request.form.get("max_sales")
        max_sales = None
        if max_sales_str and max_sales_str.strip():
            try:
                mv = int(max_sales_str)
                if mv > 0:
                    max_sales = mv
            except (ValueError, TypeError):
                pass

        # Persist the user's manual configuration so it never reverts to 20
        from sqlalchemy.orm.attributes import flag_modified
        manual_data = {
            "limit": limit,
            "module": module,
            "country": country,
            "headless": headless_str,
            "period": period_str,
            "min_sales": min_sales,
            "max_sales": max_sales
        }
        manual_setting = db.get(Setting, "manual_config")
        if not manual_setting:
            manual_setting = Setting(key="manual_config", value=manual_data, updated_by=current_user.username)
            db.add(manual_setting)
        else:
            manual_setting.value = manual_data
            manual_setting.updated_by = current_user.username
            manual_setting.updated_at = datetime.now(timezone.utc)
            flag_modified(manual_setting, "value")
        db.commit()

        run = JobService.create_daily_run(
            db,
            period_date=period_date,
            trigger="manual",
            created_by=current_user.username,
            countries=target_countries,
            module=module,
            min_sales=min_sales,
            max_sales=max_sales
        )

        # Dispatch background execution immediately
        JobService.dispatch_run_in_background(run.id, limit=limit, headless=headless)

        mode_text = "Headless" if headless else "Google Chrome (Desktop)"
        c_text = "Semua Region (ID -> MY -> TH)" if country == "ALL" else f"Region {country}"
        flash(
            f"Scraper berhasil dijalankan! Target: {c_text} (Maks: {limit} item, Mode: {mode_text}). Pantau progres di bawah.",
            "success"
        )
        return redirect(url_for("jobs.index"))
    finally:
        db.close()


@jobs_bp.route("/jobs/<job_id>")
@login_required
def detail(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(ScrapeJob, job_id)
        if not job:
            abort(404)

        screenshots = []
        if current_user.role == "admin":
            screenshots = db.execute(
                select(DiagnosticScreenshot).filter_by(scrape_job_id=job_id)
            ).scalars().all()

        return render_template(
            "jobs/detail.html",
            job=job,
            screenshots=screenshots,
            format_wib=format_wib
        )
    finally:
        db.close()


@jobs_bp.route("/jobs/cancel/<job_id>", methods=["POST"])
@admin_required
def cancel(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(ScrapeJob, job_id)
        if job and job.status in ("RUNNING", "PENDING", "BLOCKED"):
            job.status = "CANCELLED"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            flash("Job berhasil dibatalkan.", "info")
        return redirect(url_for("jobs.index"))
    finally:
        db.close()


@jobs_bp.route("/jobs/retry/<job_id>", methods=["POST"])
@admin_required
def retry_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(ScrapeJob, job_id)
        if not job:
            flash("Job tidak ditemukan.", "danger")
            return redirect(url_for("jobs.index"))

        job.status = "PENDING"
        job.started_at = None
        job.finished_at = None
        job.error_code = None
        job.error_summary = None
        db.commit()

        run_id = job.run_id or job.id
        JobService.dispatch_run_in_background(run_id, limit=200, headless=True)
        flash(f"Job scraping ({job.country_code}) berhasil dipicu ulang di latar belakang!", "success")
        return redirect(url_for("jobs.index"))
    finally:
        db.close()


@jobs_bp.route("/jobs/open-login", methods=["POST"])
@admin_required
def open_login():
    from app.services.session_service import SessionService
    from app.tasks.celery_app import open_login_browser
    db = SessionLocal()
    try:
        profile = SessionService.get_primary_profile(db)
        profile.session_status = "WAITING_FOR_VERIFICATION"
        db.commit()

        dispatched = False
        try:
            open_login_browser.delay(
                profile.profile_dir_name,
                profile.id,
                profile.account_email,
                profile.account_password
            )
            dispatched = True
        except Exception:
            pass

        if not dispatched:
            import threading
            threading.Thread(
                target=open_login_browser,
                args=(profile.profile_dir_name, profile.id, profile.account_email, profile.account_password),
                daemon=True
            ).start()

        flash(
            "Browser login dibuka di layar VNC (Port 5902) selama 15 menit. Kredensial telah otomatis terisi. "
            "Silakan buka VNC Viewer (IP_VPS:5902). Setelah login, browser akan tertutup otomatis dan scraper akan lanjut.",
            "info"
        )
        return redirect(request.referrer or url_for("jobs.index"))
    finally:
        db.close()

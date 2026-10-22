"""
Command-line interface (CLI) for Kalodata Scraper & Dashboard.
Follows rules in PRD §0.1 no. 6, §5.2, §13.3, §13.4, and §17.
"""

import sys
import json
import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import structlog
from argon2 import PasswordHasher

from app.config import settings, init_runtime_dirs, sel, SELECTORS_CONFIG
from app.models import SessionLocal, init_db
from app.models.entities import User, AccountProfile, ScrapeJob, ExportFile
from app.scrapers.base import BaseScraper
from app.scrapers.kalodata.session import SessionManager
from app.scrapers.kalodata.navigation import KalodataNavigator, NavigationError
from app.scrapers.kalodata.product_list import ProductListScraper
from app.services.job_service import JobService
from app.services.export_service import ExportService
from app.services.session_service import SessionService
from app.services.retention_service import RetentionService

logger = structlog.get_logger(__name__)
ph = PasswordHasher()


def cmd_create_admin(args):
    """Creates initial admin user (§5.2)."""
    init_db()
    db = SessionLocal()
    try:
        username = args.username
        password = args.password

        password_hash = ph.hash(password)
        existing = db.query(User).filter_by(username=username).first()
        if existing:
            existing.password_hash = password_hash
            existing.is_active = True
            existing.role = "admin"
            db.commit()
            print(f"Password untuk admin user '{username}' berhasil diperbarui / di-reset!")
            return

        admin = User(
            username=username,
            password_hash=password_hash,
            role="admin",
            is_active=True
        )
        db.add(admin)
        db.commit()
        print(f"Admin user '{username}' created successfully!")
    finally:
        db.close()


def cmd_open_login(args):
    """Opens headful browser on DISPLAY for manual login via VNC (§7.3)."""
    init_runtime_dirs()
    print(f"Launching Chromium for manual login on profile '{args.profile}'...")
    success, msg = SessionManager.launch_manual_login(
        profile_label=args.profile,
        poll_duration_min=args.duration
    )
    print(f"Result: {msg}")


def cmd_validate_session(args):
    """Validates session status for profile (§7.4)."""
    init_runtime_dirs()
    init_db()
    db = SessionLocal()
    try:
        profile = SessionService.get_or_create_default_profile(db)
        res = SessionService.validate_profile_session(db, profile.id)
        print(json.dumps(res, indent=2))
    finally:
        db.close()


def cmd_export_session(args):
    """Exports active browser session cookies to runtime/kalodata_session.json."""
    init_runtime_dirs()
    s = BaseScraper(profile_label=args.profile)
    s.acquire_lock()
    try:
        ctx = s.launch_browser(headless=True)
        session_file = settings.RUNTIME_DIR / "kalodata_session.json"
        ctx.storage_state(path=str(session_file))
        cookies_count = len(ctx.cookies())
        print(f"Session exported successfully to {session_file} ({cookies_count} cookies saved).")
    finally:
        s.close_browser()
        s.release_lock()


def cmd_import_session(args):
    """Validates and imports runtime/kalodata_session.json into profile."""
    init_runtime_dirs()
    session_file = settings.RUNTIME_DIR / "kalodata_session.json"
    if not session_file.exists():
        print(f"Error: {session_file} not found. Please upload or export it first.")
        return
    s = BaseScraper(profile_label=args.profile)
    s.acquire_lock()
    try:
        ctx = s.launch_browser(headless=True)
        page = ctx.new_page()
        status, msg = SessionManager.validate_session(page)
        print(f"Session Import & Validation: [{status}] {msg}")
    finally:
        s.close_browser()
        s.release_lock()


def cmd_smoke_selectors(args):
    """Smoke test to verify that configured selectors exist in selectors.yaml (§13.4)."""
    print(f"Verifying {len(SELECTORS_CONFIG)} selectors from config/selectors.yaml...")
    errors = []
    for name, cfg in SELECTORS_CONFIG.items():
        if not cfg.get("primary"):
            errors.append(f"Selector '{name}' is missing 'primary' key.")
        if not cfg.get("fallbacks"):
            errors.append(f"Selector '{name}' is missing 'fallbacks' list.")
        if not cfg.get("kind"):
            errors.append(f"Selector '{name}' is missing 'kind' key.")

    if errors:
        print("Smoke test FAILED:")
        for e in errors:
            print(f" - {e}")
        sys.exit(1)
    else:
        print("Smoke test PASSED: All selectors have valid structure (primary, fallbacks, kind).")


def cmd_export(args):
    """Exports job data to Excel."""
    init_runtime_dirs()
    init_db()
    db = SessionLocal()
    try:
        if args.job_id:
            exp = ExportService.export_job_results(db, args.job_id)
            if exp:
                print(f"Export created: {exp.file_name} ({exp.row_count} rows, {exp.size_bytes} bytes)")
            else:
                print("Export returned None.")
        else:
            print("Please specify --job-id")
    finally:
        db.close()


def cmd_cleanup_retention(args):
    """Executes retention cleanup."""
    init_db()
    db = SessionLocal()
    try:
        res = RetentionService.cleanup_old_data(db)
        print("Retention cleanup summary:", json.dumps(res, indent=2))
    finally:
        db.close()


def cmd_scrape(args):
    """Runs scraper for a specific country or all countries (§0.1 no. 6, §6.5)."""
    init_runtime_dirs()
    init_db()

    target_country = args.country.upper()
    limit = args.limit
    headless = args.headless

    # Determine period
    if args.period == "yesterday":
        period_date = date.today() - timedelta(days=1)
    else:
        period_date = datetime.strptime(args.period, "%Y-%m-%d").date()

    module = getattr(args, "module", "product")
    print(f"Starting Kalodata {module} scrape CLI for {target_country}, period: {period_date}, limit: {limit}...")

    db = SessionLocal()
    try:
        profile = SessionService.get_or_create_country_profile(db, target_country)
        job = ScrapeJob(
            country_code=target_country,
            module=module,
            account_profile_id=profile.id,
            period_start=period_date,
            period_end=period_date,
            status="PENDING",
            stage="INIT",
            created_by="cli"
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    JobService.execute_job_now(job_id, limit=limit, headless=headless)

    db = SessionLocal()
    try:
        final_job = db.get(ScrapeJob, job_id)
        exp = db.query(ExportFile).filter_by(scrape_job_id=job_id).first()
        summary = {
            "job_id": job_id,
            "module": module,
            "country": target_country,
            "period": str(period_date),
            "status": final_job.status if final_job else "UNKNOWN",
            "rows_saved": final_job.rows_saved if final_job else 0,
            "excel_file": exp.file_name if exp else None
        }
        print(json.dumps(summary, indent=2))
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Kalodata Scraper Dashboard CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-admin
    p_admin = subparsers.add_parser("create-admin", help="Create an admin user")
    p_admin.add_argument("--username", required=True, help="Admin username")
    p_admin.add_argument("--password", required=True, help="Admin password")
    p_admin.set_defaults(func=cmd_create_admin)

    # open-login
    p_login = subparsers.add_parser("open-login", help="Open browser on VNC DISPLAY for manual login")
    p_login.add_argument("--profile", default="default", help="Profile directory name")
    p_login.add_argument("--duration", type=int, default=20, help="Polling duration in minutes")
    p_login.set_defaults(func=cmd_open_login)

    # validate-session
    p_val = subparsers.add_parser("validate-session", help="Validate persistent profile session")
    p_val.add_argument("--profile", default="default", help="Profile directory name")
    p_val.set_defaults(func=cmd_validate_session)

    # export-session
    p_ex_sess = subparsers.add_parser("export-session", help="Export active browser session to JSON")
    p_ex_sess.add_argument("--profile", default="default", help="Profile directory name")
    p_ex_sess.set_defaults(func=cmd_export_session)

    # import-session
    p_im_sess = subparsers.add_parser("import-session", help="Import session JSON to profile")
    p_im_sess.add_argument("--profile", default="default", help="Profile directory name")
    p_im_sess.set_defaults(func=cmd_import_session)

    # smoke-selectors
    p_smoke = subparsers.add_parser("smoke-selectors", help="Smoke test config/selectors.yaml")
    p_smoke.set_defaults(func=cmd_smoke_selectors)

    # export
    p_exp = subparsers.add_parser("export", help="Export scrape job results to Excel")
    p_exp.add_argument("--job-id", required=True, help="Job UUID")
    p_exp.set_defaults(func=cmd_export)

    # cleanup-retention
    p_clean = subparsers.add_parser("cleanup-retention", help="Cleanup expired data per retention policy")
    p_clean.set_defaults(func=cmd_cleanup_retention)

    # scrape
    p_scrape = subparsers.add_parser("scrape", help="Run Kalodata scraper")
    p_scrape.add_argument("--country", required=True, choices=["ID", "MY", "TH"], help="Target country")
    p_scrape.add_argument("--module", choices=["product", "creator"], default="product", help="Module to scrape (product or creator)")
    p_scrape.add_argument("--period", default="yesterday", help="Period date (yesterday or YYYY-MM-DD)")
    p_scrape.add_argument("--limit", type=int, default=5, help="Max items/creators to scrape")
    p_scrape.add_argument("--profile", default="default", help="Account profile directory name")
    p_scrape.add_argument("--headless", action="store_true", help="Run headless mode")
    p_scrape.add_argument("--no-export", action="store_true", help="Skip Excel export generation")
    p_scrape.set_defaults(func=cmd_scrape)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

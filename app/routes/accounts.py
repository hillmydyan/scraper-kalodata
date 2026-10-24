"""
Account profile management routes (/accounts, admin only).
Follows rules in PRD §7.3, §9.3, and §14 (profile_path is never exposed).
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from sqlalchemy import select

from app.models import SessionLocal
from app.models.entities import AccountProfile, AuditLog
from app.routes.common import admin_required, format_wib
from app.services.session_service import SessionService
from app.scrapers.kalodata.session import SessionManager

accounts_bp = Blueprint("accounts", __name__)


@accounts_bp.route("/accounts")
@admin_required
def index():
    db = SessionLocal()
    try:
        primary = SessionService.get_primary_profile(db)
        country_profiles = SessionService.get_country_profiles_dict(db)
        profiles = db.execute(select(AccountProfile)).scalars().all()
        return render_template(
            "accounts/index.html",
            profiles=profiles,
            primary_profile=primary,
            indo_profile=country_profiles.get("ID"),
            thai_profile=country_profiles.get("TH"),
            format_wib=format_wib
        )
    finally:
        db.close()


@accounts_bp.route("/accounts/save", methods=["POST"])
@admin_required
def save_account():
    profile_id = (request.form.get("profile_id") or "").strip()
    country_code = (request.form.get("country_code") or "").strip().upper()
    email = (request.form.get("account_email") or "").strip()
    password = (request.form.get("account_password") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    db = SessionLocal()
    try:
        if profile_id:
            profile = db.get(AccountProfile, profile_id)
        elif country_code:
            profile = SessionService.get_or_create_country_profile(db, country_code)
        else:
            profile = SessionService.get_primary_profile(db)

        if not profile:
            profile = SessionService.get_primary_profile(db)

        profile.account_email = email
        if password:
            profile.account_password = password
        if notes:
            profile.notes = notes

        log = AuditLog(
            action="UPDATE_ACCOUNT_CREDENTIALS",
            target_type="account_profile",
            target_id=profile.id,
            details={"email": email, "updated_by": "admin"}
        )
        db.add(log)
        db.commit()

        flash("Kredensial akun Kalodata berhasil diperbarui dan disimpan!", "success")
        return redirect(url_for("accounts.index"))
    except Exception as ex:
        db.rollback()
        flash(f"Gagal menyimpan akun: {str(ex)}", "danger")
        return redirect(url_for("accounts.index"))
    finally:
        db.close()


@accounts_bp.route("/accounts/validate/<profile_id>", methods=["POST"])
@admin_required
def validate(profile_id: str):
    db = SessionLocal()
    try:
        res = SessionService.validate_profile_session(db, profile_id)
        if res.get("status") == "READY":
            flash("Sesi profil berhasil divalidasi dan AKTIF (READY).", "success")
        else:
            flash(f"Validasi sesi: {res.get('status')} - {res.get('message')}", "warning")
        return redirect(url_for("accounts.index"))
    finally:
        db.close()


@accounts_bp.route("/accounts/force-ready/<profile_id>", methods=["POST"])
@admin_required
def force_ready(profile_id: str):
    from datetime import datetime, timezone
    db = SessionLocal()
    try:
        profile = db.get(AccountProfile, profile_id)
        if profile:
            profile.session_status = "READY"
            profile.last_validated_at = datetime.now(timezone.utc)
            db.commit()
            flash("Status profil berhasil disetel ke READY! Siap untuk scraping.", "success")
        return redirect(url_for("accounts.index"))
    finally:
        db.close()


@accounts_bp.route("/accounts/unlock/<profile_id>", methods=["POST"])
@admin_required
def unlock_profile(profile_id: str):
    from app.scrapers.base import BaseScraper
    db = SessionLocal()
    try:
        profile = db.get(AccountProfile, profile_id)
        label = profile.profile_dir_name if profile else "indo"
        BaseScraper.force_unlock(label)
        BaseScraper.force_unlock("default")
        if profile and profile.session_status in ("VALIDATING", "WAITING_FOR_VERIFICATION"):
            profile.session_status = "READY"
            db.commit()
        flash(f"Lock profil '{label}' berhasil dibuka / di-reset!", "success")
        return redirect(url_for("accounts.index"))
    finally:
        db.close()


@accounts_bp.route("/accounts/open-login/<profile_id>", methods=["POST"])
@admin_required
def open_login(profile_id: str):
    import threading
    db = SessionLocal()
    try:
        profile = db.get(AccountProfile, profile_id)
        if not profile:
            flash("Profil akun tidak ditemukan.", "danger")
            return redirect(url_for("accounts.index"))

        profile.session_status = "WAITING_FOR_VERIFICATION"
        db.commit()

        label = profile.profile_dir_name
        email = profile.account_email
        password = profile.account_password

        # Dispatch ke worker container yang memiliki display VNC
        dispatched = False
        try:
            from app.tasks.celery_app import open_login_browser
            open_login_browser.delay(label, profile_id, email, password)
            dispatched = True
        except Exception as cel_err:
            pass

        if not dispatched:
            def launch_thread():
                try:
                    success, msg = SessionManager.launch_manual_login(
                        profile_label=label,
                        poll_duration_min=15,
                        email=email,
                        password=password
                    )
                    db_t = SessionLocal()
                    try:
                        p = db_t.get(AccountProfile, profile_id)
                        if p:
                            p.session_status = "READY" if success else "LOGIN_REQUIRED"
                            if success:
                                from datetime import datetime, timezone
                                p.last_validated_at = datetime.now(timezone.utc)
                            db_t.commit()

                        if success:
                            from app.models.entities import ScrapeJob
                            from app.services.job_service import JobService
                            pending_jobs = db_t.query(ScrapeJob).filter(
                                ScrapeJob.status == "PENDING"
                            ).all()
                            for pj in pending_jobs:
                                JobService.dispatch_run_in_background(pj.run_id or pj.id, limit=200, headless=True)
                    finally:
                        db_t.close()
                except Exception as ex:
                    pass

            t = threading.Thread(target=launch_thread, daemon=True)
            t.start()

        flash(
            f"Browser Chromium ({profile.account_label}) telah dibuka di layar VNC port 5902! "
            "Silakan buka VNC Viewer (2.58.82.253:5902) untuk melihat browser.",
            "success"
        )
        return redirect(url_for("accounts.index"))
    finally:
        db.close()

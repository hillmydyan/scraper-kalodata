"""
Settings and audit log route (/settings, admin only).
Follows rules in PRD §9.6 and §14.
"""

from datetime import datetime, timezone
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy import select, desc
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.models import SessionLocal
from app.models.entities import Setting, AuditLog
from app.routes.common import admin_required, format_wib
from app.services.retention_service import RetentionService
from app.services.job_service import JobService

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
@admin_required
def index():
    db = SessionLocal()
    try:
        audit_logs = db.execute(
            select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(100)
        ).scalars().all()

        current_settings = {
            "retention_excel_days": RetentionService.get_excel_retention_days(db),
            "retention_screenshot_days": settings.RETENTION_SCREENSHOT_DAYS,
            "retention_log_days": settings.RETENTION_LOG_DAYS,
            "export_empty_file": settings.EXPORT_EMPTY_FILE,
            "max_products": settings.MAX_PRODUCTS_PER_COUNTRY,
            "readiness_hour": settings.READINESS_DEADLINE_HOUR_WIB,
            "webhook_url": settings.WEBHOOK_URL or "",
            "min_product_sales": JobService.get_min_product_sales(db),
            "max_product_sales": JobService.get_max_product_sales(db)
        }

        return render_template(
            "settings/index.html",
            settings=current_settings,
            audit_logs=audit_logs,
            format_wib=format_wib
        )
    finally:
        db.close()


@settings_bp.route("/settings/retention", methods=["POST"])
@admin_required
def update_retention():
    excel_days_str = request.form.get("retention_excel_days", "5")
    try:
        excel_days = max(1, int(excel_days_str))
    except (ValueError, TypeError):
        excel_days = 5

    db = SessionLocal()
    try:
        st = db.get(Setting, "retention_excel_days")
        if not st:
            st = Setting(key="retention_excel_days", value=excel_days, updated_by=current_user.username)
            db.add(st)
        else:
            st.value = excel_days
            st.updated_by = current_user.username
            st.updated_at = datetime.now(timezone.utc)
            flag_modified(st, "value")

        # Run cleanup immediately
        clean_res = RetentionService.cleanup_old_data(db)
        db.commit()

        flash(
            f"Kebijakan retensi berhasil diperbarui menjadi {excel_days} hari! ({clean_res['excel_deleted']} berkas lama dibersihkan)",
            "success"
        )
    finally:
        db.close()

    return redirect(url_for("settings.index"))


@settings_bp.route("/settings/min-sales", methods=["POST"])
@admin_required
def update_min_sales():
    min_sales_str = request.form.get("min_product_sales", "150")
    max_sales_str = request.form.get("max_product_sales", "")
    try:
        min_sales = max(1, int(min_sales_str))
    except (ValueError, TypeError):
        min_sales = 150

    max_sales = None
    if max_sales_str and max_sales_str.strip():
        try:
            val = int(max_sales_str)
            if val > 0:
                max_sales = val
        except (ValueError, TypeError):
            pass

    db = SessionLocal()
    try:
        st_min = db.get(Setting, "min_product_sales")
        if not st_min:
            st_min = Setting(key="min_product_sales", value=min_sales, updated_by=current_user.username)
            db.add(st_min)
        else:
            st_min.value = min_sales
            st_min.updated_by = current_user.username
            st_min.updated_at = datetime.now(timezone.utc)
            flag_modified(st_min, "value")

        st_max = db.get(Setting, "max_product_sales")
        if not st_max:
            st_max = Setting(key="max_product_sales", value=max_sales, updated_by=current_user.username)
            db.add(st_max)
        else:
            st_max.value = max_sales
            st_max.updated_by = current_user.username
            st_max.updated_at = datetime.now(timezone.utc)
            flag_modified(st_max, "value")

        db.commit()

        range_desc = f"{min_sales} s/d {max_sales} pcs" if max_sales else f"minimal {min_sales} pcs"
        flash(
            f"Rentang penjualan produk berhasil diperbarui menjadi {range_desc}!",
            "success"
        )
    finally:
        db.close()

    return redirect(url_for("settings.index"))

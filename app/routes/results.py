"""
Results and Export download routes (/results).
Follows rules in PRD §9.2 and §14 (Security: path validation, RBAC re-export).
"""

from pathlib import Path
from flask import Blueprint, render_template, request, send_file, abort, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import select, desc

from app.config import settings
from app.models import SessionLocal
from app.models.entities import ExportFile, ScrapeJob, KalodataProductResult
from app.routes.common import admin_required, format_wib
from app.services.export_service import ExportService

results_bp = Blueprint("results", __name__)


from sqlalchemy import select, desc, func, or_

@results_bp.route("/results")
@login_required
def index():
    active_module = request.args.get("module", "product").lower()
    if active_module not in ("product", "creator"):
        active_module = "product"

    country = request.args.get("country")
    status = request.args.get("status")

    db = SessionLocal()
    try:
        query = select(ExportFile).filter(ExportFile.deleted_at.is_(None))

        if active_module == "creator":
            query = query.filter(ExportFile.module == "creator")
        else:
            query = query.filter(or_(ExportFile.module == "product", ExportFile.module.is_(None)))

        if country:
            query = query.filter(ExportFile.country_code == country)
        if status:
            query = query.filter(ExportFile.status == status)

        query = query.order_by(desc(ExportFile.created_at)).limit(100)
        export_files = db.execute(query).scalars().all()

        # Tab counts
        product_count = db.execute(
            select(func.count(ExportFile.id)).filter(
                ExportFile.deleted_at.is_(None),
                or_(ExportFile.module == "product", ExportFile.module.is_(None))
            )
        ).scalar() or 0

        creator_count = db.execute(
            select(func.count(ExportFile.id)).filter(
                ExportFile.deleted_at.is_(None),
                ExportFile.module == "creator"
            )
        ).scalar() or 0

        return render_template(
            "results/index.html",
            export_files=export_files,
            selected_country=country,
            selected_status=status,
            active_module=active_module,
            product_count=product_count,
            creator_count=creator_count,
            format_wib=format_wib
        )
    finally:
        db.close()


@results_bp.route("/results/products")
@login_required
def products():
    return redirect(url_for("results.index", module="product"))


@results_bp.route("/results/creators")
@login_required
def creators():
    return redirect(url_for("results.index", module="creator"))


@results_bp.route("/results/download/<file_id>")
@login_required
def download(file_id: str):
    db = SessionLocal()
    try:
        exp = db.get(ExportFile, file_id)
        if not exp or exp.deleted_at is not None:
            abort(404)

        # Path traversal guard (§14)
        if ".." in exp.relative_path or exp.relative_path.startswith("/"):
            abort(400)

        target_file = (settings.RUNTIME_DIR / "exports" / exp.relative_path).resolve()
        exports_root = (settings.RUNTIME_DIR / "exports").resolve()

        if not str(target_file).startswith(str(exports_root)) or not target_file.exists():
            abort(404)

        return send_file(
            target_file,
            as_attachment=True,
            download_name=exp.file_name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    finally:
        db.close()


from app.models.entities import ExportFile, ScrapeJob, KalodataProductResult, KalodataCreatorProductResult

@results_bp.route("/results/preview/<job_id>")
@login_required
def preview(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(ScrapeJob, job_id)
        if not job:
            abort(404)

        # Allow customizable preview limit (default 200, 'all' for unlimited)
        raw_limit = request.args.get("limit", "200")
        if raw_limit.lower() == "all":
            query_limit = None
        else:
            try:
                query_limit = max(1, int(raw_limit))
            except ValueError:
                query_limit = 200

        if job.module == "creator":
            stmt = (
                select(KalodataCreatorProductResult)
                .filter_by(scrape_job_id=job_id)
                .order_by(
                    KalodataCreatorProductResult.creator_rank.asc().nullslast(),
                    KalodataCreatorProductResult.creator_name.asc(),
                    KalodataCreatorProductResult.product_rank.asc().nullslast(),
                    KalodataCreatorProductResult.revenue_value.desc().nullslast()
                )
            )
            if query_limit is not None:
                stmt = stmt.limit(query_limit)
            results = db.execute(stmt).scalars().all()
        else:
            stmt = (
                select(KalodataProductResult)
                .filter_by(scrape_job_id=job_id)
                .order_by(KalodataProductResult.revenue_value.desc().nullslast())
            )
            if query_limit is not None:
                stmt = stmt.limit(query_limit)
            results = db.execute(stmt).scalars().all()

        return render_template(
            "results/preview.html",
            job=job,
            results=results,
            preview_limit=query_limit,
            format_wib=format_wib
        )
    finally:
        db.close()


@results_bp.route("/results/reexport/<job_id>", methods=["POST"])
@admin_required
def reexport(job_id: str):
    db = SessionLocal()
    try:
        new_exp = ExportService.export_job_results(db, job_id, force_reexport=True)
        if new_exp:
            flash(f"Ekspor ulang berhasil dibuat: {new_exp.file_name}", "success")
        else:
            flash("Gagal membuat ekspor ulang.", "danger")
        return redirect(url_for("results.index"))
    finally:
        db.close()

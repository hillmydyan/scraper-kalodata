"""
Insight harian produk (/insights): perbandingan hari ini vs periode sebelumnya + ringkasan AI.
"""

from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import select, desc

from app.models import SessionLocal
from app.models.entities import DailyProductInsight, KalodataProductResult
from app.services import insight_service, llm_client

insights_bp = Blueprint("insights", __name__)

COUNTRIES = ("ID", "MY", "TH")


def _available_periods(db, country):
    stmt = (
        select(KalodataProductResult.period_start)
        .where(KalodataProductResult.country_code == country)
        .distinct()
        .order_by(desc(KalodataProductResult.period_start))
        .limit(60)
    )
    return [r for r in db.execute(stmt).scalars().all()]


@insights_bp.route("/insights")
@login_required
def index():
    country = (request.args.get("country") or "ID").upper()
    if country not in COUNTRIES:
        country = "ID"
    db = SessionLocal()
    try:
        periods = _available_periods(db, country)
        period = None
        if request.args.get("period"):
            try:
                period = date.fromisoformat(request.args["period"])
            except ValueError:
                period = None
        if period is None and periods:
            period = periods[0]

        insight = None
        if period:
            insight = db.execute(
                select(DailyProductInsight).where(
                    DailyProductInsight.country_code == country,
                    DailyProductInsight.period_start == period,
                )
            ).scalar_one_or_none()
            # Belum ada? hitung diff saja (tanpa AI) supaya halaman langsung berisi.
            if insight is None:
                insight = insight_service.build_insight(db, country, period, with_ai=False)

        return render_template(
            "insights/index.html",
            countries=COUNTRIES,
            selected_country=country,
            periods=periods,
            selected_period=period,
            insight=insight,
            diff=(insight.diff if insight else None),
            ai_enabled=llm_client.is_enabled(),
        )
    finally:
        db.close()


@insights_bp.route("/insights/rebuild", methods=["POST"])
@login_required
def rebuild():
    country = (request.form.get("country") or "ID").upper()
    try:
        period = date.fromisoformat(request.form.get("period", ""))
    except ValueError:
        flash("Periode tidak valid.", "error")
        return redirect(url_for("insights.index", country=country))
    db = SessionLocal()
    try:
        insight_service.build_insight(db, country, period, with_ai=False)
        flash("Perbandingan diperbarui.", "success")
    finally:
        db.close()
    return redirect(url_for("insights.index", country=country, period=period.isoformat()))

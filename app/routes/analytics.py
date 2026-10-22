"""
Analytics and Smart Insights routes (/analytics).
Identifies high-revenue, low-commission opportunities automatically.
"""

from datetime import datetime
from flask import Blueprint, render_template, request, send_file, jsonify, abort
from flask_login import login_required

from app.models import SessionLocal
from app.services.analytics_service import AnalyticsService
from app.routes.common import format_wib

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
@login_required
def index():
    country = request.args.get("country", "")
    module = request.args.get("module", "all")
    max_comm_str = request.args.get("max_comm", "5")
    min_rev_str = request.args.get("min_rev", "0")
    tier_filter = request.args.get("tier", "ALL")
    search_q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort", "sales")

    try:
        max_comm = float(max_comm_str) / 100.0
    except (ValueError, TypeError):
        max_comm = 0.05

    try:
        min_rev = float(min_rev_str)
    except (ValueError, TypeError):
        min_rev = 0.0

    db = SessionLocal()
    try:
        data = AnalyticsService.get_analyzed_items(
            db=db,
            country=country if country else None,
            module=module,
            max_commission=max_comm,
            min_revenue=min_rev,
            tier_filter=tier_filter,
            search_query=search_q if search_q else None,
            sort_by=sort_by
        )

        return render_template(
            "analytics/index.html",
            items=data["items"],
            kpis=data["kpis"],
            chart=data["chart"],
            selected_country=country,
            selected_module=module,
            selected_max_comm=max_comm_str,
            selected_min_rev=min_rev_str,
            selected_tier=tier_filter,
            selected_sort=sort_by,
            search_q=search_q,
            format_wib=format_wib
        )
    finally:
        db.close()


@analytics_bp.route("/analytics/api/data")
@login_required
def api_data():
    country = request.args.get("country", "")
    module = request.args.get("module", "all")
    max_comm_str = request.args.get("max_comm", "5")
    min_rev_str = request.args.get("min_rev", "0")
    tier_filter = request.args.get("tier", "ALL")
    search_q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort", "sales")

    try:
        max_comm = float(max_comm_str) / 100.0
    except (ValueError, TypeError):
        max_comm = 0.05

    try:
        min_rev = float(min_rev_str)
    except (ValueError, TypeError):
        min_rev = 0.0

    db = SessionLocal()
    try:
        data = AnalyticsService.get_analyzed_items(
            db=db,
            country=country if country else None,
            module=module,
            max_commission=max_comm,
            min_revenue=min_rev,
            tier_filter=tier_filter,
            search_query=search_q if search_q else None,
            sort_by=sort_by
        )
        return jsonify({
            "status": "success",
            "kpis": data["kpis"],
            "chart": data["chart"],
            "total_count": len(data["items"])
        })
    finally:
        db.close()


@analytics_bp.route("/analytics/export")
@login_required
def export_excel():
    country = request.args.get("country", "")
    module = request.args.get("module", "all")
    max_comm_str = request.args.get("max_comm", "5")
    min_rev_str = request.args.get("min_rev", "0")
    tier_filter = request.args.get("tier", "ALL")
    search_q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort", "sales")

    try:
        max_comm = float(max_comm_str) / 100.0
    except (ValueError, TypeError):
        max_comm = 0.05

    try:
        min_rev = float(min_rev_str)
    except (ValueError, TypeError):
        min_rev = 0.0

    db = SessionLocal()
    try:
        data = AnalyticsService.get_analyzed_items(
            db=db,
            country=country if country else None,
            module=module,
            max_commission=max_comm,
            min_revenue=min_rev,
            tier_filter=tier_filter,
            search_query=search_q if search_q else None,
            sort_by=sort_by
        )

        excel_stream = AnalyticsService.generate_excel_export(data["items"])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Smart_Analytics_Peluang_Emas_{timestamp}.xlsx"

        return send_file(
            excel_stream,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    finally:
        db.close()

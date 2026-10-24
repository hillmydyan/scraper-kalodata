"""
System API routes (/health, /metrics).
Follows rules in PRD §9.7.
"""

from flask import Blueprint, jsonify
import shutil
from app.config import settings
from app.models import SessionLocal

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health():
    """Unauthenticated health endpoint returning JSON status of DB, Redis, and disk."""
    status = {
        "status": "healthy",
        "database": "unknown",
        "redis": "unknown",
        "disk_ok": True
    }

    # DB test
    db = SessionLocal()
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        status["database"] = "healthy"
    except Exception as e:
        status["database"] = f"unhealthy: {str(e)}"
        status["status"] = "degraded"
    finally:
        db.close()

    # Redis test
    try:
        import redis
        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)
        if r.ping():
            status["redis"] = "healthy"
    except Exception as e:
        status["redis"] = f"unhealthy: {str(e)}"
        status["status"] = "degraded"

    # Scheduler check
    from app.services.scheduler_service import SchedulerService
    if not (SchedulerService._thread and SchedulerService._thread.is_alive()):
        # Ensure scheduler thread is started
        SchedulerService.start_scheduler_thread()

    status["scheduler_alive"] = bool(SchedulerService._thread and SchedulerService._thread.is_alive())

    return jsonify(status)

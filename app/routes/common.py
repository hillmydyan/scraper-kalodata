"""
Common route helpers, decorators, and context processors.
Follows rules in PRD §5 (RBAC) and §9.
"""

from functools import wraps
from datetime import datetime
from flask import abort, redirect, url_for, flash
from flask_login import current_user
import zoneinfo

WIB = zoneinfo.ZoneInfo("Asia/Jakarta")


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.role != "admin":
            flash("Akses ditolak: Fitur ini hanya untuk Administrator.", "danger")
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def format_wib(dt: datetime) -> str:
    """Formats UTC datetime to WIB string."""
    if not dt:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
    return dt.astimezone(WIB).strftime("%d %b %Y %H:%M WIB")

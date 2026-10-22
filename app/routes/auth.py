"""
Authentication routes: login, logout.
Follows rules in PRD §5, §9.7, and §14.
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.models import SessionLocal
from app.models.entities import User, AuditLog

auth_bp = Blueprint("auth", __name__)
ph = PasswordHasher()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username=username).first()
            if user and user.is_active:
                try:
                    ph.verify(user.password_hash, password)
                    login_user(user)

                    # Audit log
                    log = AuditLog(
                        actor_id=user.username,
                        action="LOGIN_SUCCESS",
                        target_type="user",
                        target_id=user.id,
                        ip=request.remote_addr
                    )
                    db.add(log)
                    db.commit()

                    flash("Selamat datang kembali!", "success")
                    next_page = request.args.get("next")
                    return redirect(next_page or url_for("dashboard.index"))
                except VerifyMismatchError:
                    pass

            flash("Username atau password salah.", "danger")
        finally:
            db.close()

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Anda telah berhasil logout.", "info")
    return redirect(url_for("auth.login"))

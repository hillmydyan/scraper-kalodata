"""
Flask Application Factory for Kalodata Scraper & Dashboard.
Follows rules in PRD §5, §9, and §14.
"""

from flask import Flask, redirect, url_for, flash
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError

from app.config import settings
from app.models import SessionLocal, init_db
from app.models.entities import User

login_manager = LoginManager()
csrf = CSRFProtect()


@login_manager.user_loader
def load_user(user_id: str):
    db = SessionLocal()
    try:
        return db.get(User, user_id)
    finally:
        db.close()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.SECRET_KEY
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True

    # Initialize extensions
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Silakan login terlebih dahulu untuk mengakses halaman ini."
    login_manager.login_message_category = "warning"
    csrf.init_app(app)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        flash("Sesi form telah kedaluwarsa. Silakan coba lagi.", "warning")
        return redirect(url_for("auth.login"))

    # Initialize DB
    init_db()

    # Global Jinja Helpers & Filters
    from app.routes.common import format_wib

    @app.context_processor
    def inject_helpers():
        return dict(format_wib=format_wib)

    app.jinja_env.filters["format_wib"] = format_wib

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.results import results_bp
    from app.routes.accounts import accounts_bp
    from app.routes.jobs import jobs_bp
    from app.routes.settings import settings_bp
    from app.routes.api import api_bp
    from app.routes.analytics import analytics_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(analytics_bp)

    return app

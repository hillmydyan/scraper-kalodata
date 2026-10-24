"""
Account profile and session service.
Follows rules in PRD §7.4, §7.5, and §9.3.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AccountProfile, AuditLog
from app.scrapers.base import BaseScraper
from app.scrapers.kalodata.session import SessionManager

logger = structlog.get_logger(__name__)


class SessionService:
    @staticmethod
    def get_primary_profile(db: Session) -> AccountProfile:
        """
        Returns or initializes the primary multi-region Kalodata account profile
        which covers ID (Indonesia), MY (Malaysia), and TH (Thailand).
        """
        # Look for existing primary / indo / default profile
        profile = db.execute(
            select(AccountProfile).filter(
                AccountProfile.account_label.in_(["indo", "main", "default"])
            )
        ).scalars().first()

        if profile:
            # Ensure country scope includes all 3 active regions
            current_scope = set(profile.country_scope or [])
            if not {"ID", "MY", "TH"}.issubset(current_scope):
                profile.country_scope = ["ID", "MY", "TH"]
                if not profile.notes or "Thailand" not in profile.notes:
                    profile.notes = "Akun Utama Kalodata Multi-Region (ID, MY, TH)"
            # Set default credentials if not yet set
            if not profile.account_email:
                profile.account_email = "pohon.cemara0706@gmail.com"
                profile.account_password = "wisnu6696!"
            db.commit()
            return profile

        # If no profile found, create the unified multi-region profile
        profile = AccountProfile(
            source="kalodata",
            account_label="indo",
            country_scope=["ID", "MY", "TH"],
            profile_dir_name="indo",
            session_status="WAITING_FOR_VERIFICATION",
            account_email="pohon.cemara0706@gmail.com",
            account_password="wisnu6696!",
            notes="Akun Utama Kalodata Multi-Region (ID, MY, TH)"
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    @staticmethod
    def get_or_create_default_profile(db: Session) -> AccountProfile:
        return SessionService.get_primary_profile(db)

    @staticmethod
    def get_or_create_country_profile(db: Session, country_code: str) -> AccountProfile:
        """
        Single account now handles 3+ regions (ID, MY, TH).
        Returns the unified primary profile for any target country.
        """
        return SessionService.get_primary_profile(db)

    @staticmethod
    def get_country_profiles_dict(db: Session) -> Dict[str, AccountProfile]:
        """Returns dict containing unified profile mapped to all regions."""
        primary = SessionService.get_primary_profile(db)
        return {
            "ALL": primary,
            "ID": primary,
            "MY": primary,
            "TH": primary
        }

    @staticmethod
    def validate_profile_session(db: Session, profile_id: str) -> Dict[str, Any]:
        """Validates profile session using browser check."""
        profile = db.get(AccountProfile, profile_id)
        if not profile:
            return {"status": "ERROR", "message": "Profile not found"}

        profile.session_status = "VALIDATING"
        db.commit()

        scraper = BaseScraper(profile_label=profile.profile_dir_name)
        try:
            scraper.acquire_lock()
            context = scraper.launch_browser(headless=True)
            page = context.new_page()
            status, message = SessionManager.validate_session(page, timeout_sec=25)

            profile.session_status = status
            if status == "READY":
                profile.last_validated_at = datetime.now(timezone.utc)

            # Audit log
            log = AuditLog(
                action="VALIDATE_SESSION",
                target_type="account_profile",
                target_id=profile.id,
                details={"status": status, "message": message}
            )
            db.add(log)
            db.commit()
            return {"status": status, "message": message}
        except Exception as e:
            logger.warning("Session validation encountered an error", error=str(e))
            profile.session_status = "ERROR"
            db.commit()
            return {"status": "ERROR", "message": str(e)}
        finally:
            scraper.close_browser()
            scraper.release_lock()


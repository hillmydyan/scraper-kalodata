"""
Session validator and manual login manager for Kalodata.
Follows rules in PRD §7.3, §7.4, and §7.5.
"""

import time
from datetime import datetime, timezone
from typing import Tuple, Optional
import structlog
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from app.config import settings, sel
from app.scrapers.base import BaseScraper

logger = structlog.get_logger(__name__)


class SessionManager:
    @staticmethod
    def is_challenge_active(page: Page) -> bool:
        return BaseScraper.is_challenge_active(page)

    @staticmethod
    def check_and_wait_for_challenge(
        page: Page,
        job_id: Optional[str] = None,
        max_wait_sec: int = 180,
        cancel_check_cb=None
    ) -> Tuple[bool, str]:
        return BaseScraper.wait_for_challenge(page, job_id=job_id, max_wait_sec=max_wait_sec, cancel_check_cb=cancel_check_cb)

    @staticmethod
    def wait_for_manual_login(
        page: Page,
        job_id: Optional[str] = None,
        max_wait_sec: int = 900,
        cancel_check_cb=None
    ) -> Tuple[bool, str]:
        """
        Pauses and keeps the browser on Kalodata login page in VNC (Port 5902)
        for 10-15 minutes so the operator can complete login.
        Auto-fills credentials if available. Once logged in, returns True.
        """
        from app.services.job_service import JobService
        from app.services.session_service import SessionService
        from app.models import SessionLocal

        if job_id:
            JobService.set_job_status(
                job_id=job_id,
                status="BLOCKED",
                stage="WAITING_LOGIN",
                error_summary="Akun belum login ke Kalodata. Browser login terbuka di VNC (Port 5902) selama 15 menit. Silakan selesaikan login di VNC Viewer, job akan otomatis lanjut setelah Anda login."
            )

        # Retrieve configured email & password
        email = None
        password = None
        db = SessionLocal()
        try:
            profile = SessionService.get_primary_profile(db)
            if profile:
                email = profile.account_email or "pohon.cemara0706@gmail.com"
                password = profile.account_password or "wisnu6696!"
        finally:
            db.close()

        # Ensure page is on login page
        login_url = f"{settings.KALODATA_BASE_URL.rstrip('/')}/login"
        curr_url = (page.url or "").lower()
        if "login" not in curr_url and "signin" not in curr_url:
            try:
                page.goto(login_url, wait_until="domcontentloaded", timeout=25000)
            except Exception:
                pass

        # Auto-fill credentials and auto-submit
        if email and password:
            try:
                time.sleep(2)
                email_input = page.locator('input[type="email"], input[placeholder*="email" i], input[type="text"]').first
                if email_input.is_visible(timeout=3000):
                    email_input.fill(email)
                pwd_input = page.locator('input[type="password"]').first
                if pwd_input.is_visible(timeout=3000):
                    pwd_input.fill(password)

                try:
                    remember_cb = page.locator("input[type='checkbox'], .remember-me, label:has-text('Remember')").first
                    if remember_cb.is_visible(timeout=1000) and not remember_cb.is_checked():
                        remember_cb.click()
                except Exception:
                    pass

                time.sleep(1)
                submit_btn = page.locator("button[type='submit'], button:has-text('Sign In'), button:has-text('Log In'), button:has-text('Masuk'), .login-btn").first
                if submit_btn.is_visible(timeout=2000):
                    logger.info("Auto-submitting Kalodata login form...")
                    submit_btn.click()
            except Exception as e:
                logger.debug("Auto-fill login skipped", error=str(e))

        start_time = time.time()
        while time.time() - start_time < max_wait_sec:
            if cancel_check_cb and cancel_check_cb():
                logger.info("Scrape job cancelled while waiting for login in VNC", job_id=job_id)
                return False, "CANCELLED"

            time.sleep(3)

            try:
                c_url = (page.url or "").lower()
                # Check if redirected away from login and not on Cloudflare challenge
                if "login" not in c_url and "signin" not in c_url and "about:blank" not in c_url and not BaseScraper.is_challenge_active(page):
                    logger.info("Login confirmed! Continuing scrape job...", job_id=job_id, url=page.url)
                    time.sleep(3)  # Allow cookies to flush

                    if job_id:
                        JobService.set_job_status(
                            job_id=job_id,
                            status="RUNNING",
                            stage="STARTING",
                            error_summary=None
                        )

                    # Update profile session_status in DB
                    db_up = SessionLocal()
                    try:
                        p = SessionService.get_primary_profile(db_up)
                        p.session_status = "READY"
                        p.last_validated_at = datetime.now(timezone.utc)
                        db_up.commit()
                    finally:
                        db_up.close()

                    return True, "RESOLVED"
            except Exception:
                pass

        logger.warning("Timed out waiting for manual login in VNC (15 min)", job_id=job_id)
        if job_id:
            JobService.set_job_status(
                job_id=job_id,
                status="PENDING",
                stage="WAITING_LOGIN",
                error_summary="Batas waktu login (15 menit) habis di VNC Viewer. Silakan klik 'Buka Browser Login' saat Anda siap."
            )
        return False, "TIMEOUT"

    @staticmethod
    def validate_session(
        page: Page,
        timeout_sec: int = 30,
        job_id: Optional[str] = None,
        wait_for_human: bool = False,
        max_human_wait_sec: int = 900,
        cancel_check_cb=None
    ) -> Tuple[str, str]:
        """
        Validates if current persistent profile session is logged in (§7.4).
        If wait_for_human is True and Cloudflare or login is required,
        pauses and waits for manual VNC interaction up to 15 minutes.
        Returns:
            (status, message)
            status is one of: 'READY', 'LOGIN_REQUIRED', 'ERROR', 'ACCESS_RESTRICTED', 'CANCELLED'
        """
        target_url = f"{settings.KALODATA_BASE_URL.rstrip('/')}/product"
        logger.info("Validating session on page", url=target_url)

        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            BaseScraper.pacing_page_delay()
        except PlaywrightTimeoutError:
            return "ERROR", "Timeout navigating to Kalodata product page."
        except Exception as e:
            return "ERROR", f"Network error during session validation: {str(e)}"

        # 1. Check for genuine Cloudflare challenge
        if BaseScraper.is_challenge_active(page):
            if wait_for_human:
                cleared, reason = BaseScraper.wait_for_challenge(
                    page=page,
                    job_id=job_id,
                    max_wait_sec=max_human_wait_sec,
                    cancel_check_cb=cancel_check_cb
                )
                if not cleared:
                    if reason == "CANCELLED":
                        return "CANCELLED", "Job dibatalkan oleh pengguna saat menunggu verifikasi Cloudflare."
                    return "ACCESS_RESTRICTED", "Timeout menunggu penyelesaian Cloudflare di VNC Viewer (Port 5902)."
            else:
                return "ACCESS_RESTRICTED", "Cloudflare verification challenge page detected (Just a moment...)."

        # 2. Check if redirected to login page or login indicator is present
        current_url = (page.url or "").lower()
        is_login_page = ("login" in current_url or "signin" in current_url)
        if not is_login_page:
            login_page_cfg = sel("login_page_indicator")
            for selector in [login_page_cfg["primary"]] + login_page_cfg.get("fallbacks", []):
                try:
                    if page.locator(selector).first.is_visible(timeout=500):
                        is_login_page = True
                        break
                except Exception:
                    pass

        if is_login_page:
            if wait_for_human:
                logger.warning(
                    "Session requires login! Pausing for manual login in VNC Viewer (port 5902)...",
                    job_id=job_id,
                    max_wait_sec=max_human_wait_sec
                )
                cleared, reason = SessionManager.wait_for_manual_login(
                    page=page,
                    job_id=job_id,
                    max_wait_sec=max_human_wait_sec,
                    cancel_check_cb=cancel_check_cb
                )
                if cleared:
                    return "READY", "Login berhasil via VNC dan sesi aktif."
                if reason == "CANCELLED":
                    return "CANCELLED", "Job dibatalkan oleh pengguna saat menunggu login."
                return "LOGIN_REQUIRED", "Batas waktu login (15 menit) habis di VNC Viewer (Port 5902)."
            else:
                return "LOGIN_REQUIRED", "Login required. Sesi belum login ke Kalodata."

        # 3. Check logged-in indicators
        logged_in_cfg = sel("logged_in_indicator")
        for selector in [logged_in_cfg["primary"]] + logged_in_cfg.get("fallbacks", []):
            try:
                if page.locator(selector).first.is_visible(timeout=500):
                    logger.info("Session verified: logged in indicator found", selector=selector)
                    return "READY", "Session is valid and active."
            except Exception:
                pass

        # If neither login form nor block is shown, page loaded normally
        if "product" in current_url or "kalodata.com" in current_url:
            logger.info("Session ready: product page accessible without login form")
            return "READY", "Halaman Kalodata berhasil dimuat."

        return "READY", "Page loaded without login redirection."

    @staticmethod
    def launch_manual_login(
        profile_label: str = "default",
        poll_duration_min: int = 15,
        email: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Launches headful browser on VNC DISPLAY for manual login (§7.3).
        Browser remains open for 10-15 minutes or closes immediately once login is detected.
        Auto-fills credentials and auto-submits.
        """
        scraper = BaseScraper(profile_label=profile_label)
        scraper.acquire_lock()
        try:
            context = scraper.launch_browser(headless=False)
            page = context.new_page()
            login_url = f"{settings.KALODATA_BASE_URL.rstrip('/')}/login"
            logger.info("Opening manual login browser on VNC DISPLAY", url=login_url, profile=profile_label)
            page.goto(login_url, wait_until="domcontentloaded")

            # Fallback credentials if not provided
            if not email or not password:
                from app.models import SessionLocal
                from app.services.session_service import SessionService
                db = SessionLocal()
                try:
                    p = SessionService.get_primary_profile(db)
                    email = email or p.account_email or "pohon.cemara0706@gmail.com"
                    password = password or p.account_password or "wisnu6696!"
                finally:
                    db.close()

            # Auto-fill credentials and auto-submit if provided
            if email and password:
                try:
                    time.sleep(2)
                    email_input = page.locator('input[type="email"], input[placeholder*="email" i], input[type="text"]').first
                    if email_input.is_visible(timeout=3000):
                        email_input.fill(email)
                    pwd_input = page.locator('input[type="password"]').first
                    if pwd_input.is_visible(timeout=3000):
                        pwd_input.fill(password)

                    # Auto-check Remember Me if present
                    try:
                        remember_cb = page.locator("input[type='checkbox'], .remember-me, label:has-text('Remember')").first
                        if remember_cb.is_visible(timeout=1000) and not remember_cb.is_checked():
                            remember_cb.click()
                    except Exception:
                        pass

                    # Auto-click Login / Submit button
                    time.sleep(1)
                    submit_btn = page.locator("button[type='submit'], button:has-text('Sign In'), button:has-text('Log In'), button:has-text('Masuk'), .login-btn").first
                    if submit_btn.is_visible(timeout=2000):
                        logger.info("Auto-submitting login form for Kalodata...")
                        submit_btn.click()
                except Exception as fill_err:
                    logger.debug("Auto-fill attempt skipped or failed", error=str(fill_err))

            start_poll = time.time()
            max_seconds = poll_duration_min * 60
            while time.time() - start_poll < max_seconds:
                time.sleep(3)
                try:
                    curr_url = (page.url or "").lower()
                    # Check if user successfully submitted login and navigated away from login page without sitting on challenge
                    if "login" not in curr_url and "signin" not in curr_url and "about:blank" not in curr_url and not BaseScraper.is_challenge_active(page):
                        logger.info("Manual login detected via URL redirect! Closing browser gracefully...", url=page.url)
                        time.sleep(4)  # Allow cookies and token to flush to disk
                        return True, "Login berhasil dan sesi tersimpan permanen."
                except Exception:
                    # User closed the browser window manually
                    logger.info("Browser window closed by user.")
                    break

            return False, "Batas waktu login manual (15 menit) selesai."
        finally:
            scraper.close_browser()
            scraper.release_lock()

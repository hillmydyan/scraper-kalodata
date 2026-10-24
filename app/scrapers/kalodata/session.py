"""
Session validator and manual login manager for Kalodata.
Follows rules in PRD §7.3, §7.4, and §7.5.
"""

import time
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
    def validate_session(
        page: Page,
        timeout_sec: int = 30,
        job_id: Optional[str] = None,
        wait_for_human: bool = False,
        max_human_wait_sec: int = 180,
        cancel_check_cb=None
    ) -> Tuple[str, str]:
        """
        Validates if current persistent profile session is logged in (§7.4).
        If wait_for_human is True and Cloudflare is detected, pauses and waits for manual VNC click.
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

        # Check for genuine Cloudflare challenge
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

        # Check if redirected to login page
        current_url = page.url.lower()
        if "login" in current_url or "signin" in current_url:
            return "LOGIN_REQUIRED", "Login required. Sesi belum login ke Kalodata."

        # Fetch selector configs
        logged_in_cfg = sel("logged_in_indicator")
        login_page_cfg = sel("login_page_indicator")

        # Check login page indicators (password inputs)
        for selector in [login_page_cfg["primary"]] + login_page_cfg.get("fallbacks", []):
            try:
                if page.locator(selector).first.is_visible(timeout=500):
                    logger.info("Session invalid: login indicator found", selector=selector)
                    return "LOGIN_REQUIRED", "Login required. Halaman menampilkan form login."
            except Exception:
                pass

        # Check logged-in indicators
        for selector in [logged_in_cfg["primary"]] + logged_in_cfg.get("fallbacks", []):
            try:
                if page.locator(selector).first.is_visible(timeout=500):
                    logger.info("Session verified: logged in indicator found", selector=selector)
                    return "READY", "Session is valid and active."
            except Exception:
                pass

        # If neither login form nor block is shown, page loaded normally
        if "product" in page.url.lower() or "kalodata.com" in page.url.lower():
            logger.info("Session ready: product page accessible without login form")
            return "READY", "Halaman Kalodata berhasil dimuat."

        return "READY", "Page loaded without login redirection."

    @staticmethod
    def launch_manual_login(
        profile_label: str = "default",
        poll_duration_min: int = 20,
        email: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Launches headful browser for manual login (§7.3).
        Polls for verification without interrupting user typing.
        Can optionally auto-fill credentials if provided.
        """
        scraper = BaseScraper(profile_label=profile_label)
        scraper.acquire_lock()
        try:
            context = scraper.launch_browser(headless=False)
            page = context.new_page()
            login_url = f"{settings.KALODATA_BASE_URL.rstrip('/')}/login"
            logger.info("Opening manual login browser for user", url=login_url, profile=profile_label)
            page.goto(login_url, wait_until="domcontentloaded")

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
                    curr_url = page.url.lower()
                    # Check if user successfully submitted login and navigated away from login page without sitting on challenge
                    if "login" not in curr_url and "signin" not in curr_url and "about:blank" not in curr_url and not BaseScraper.is_challenge_active(page):
                        logger.info("Manual login detected via URL redirect", url=page.url)
                        time.sleep(3)  # Allow cookies to flush
                        return True, "Login successful and session validated."
                except Exception:
                    # User closed the browser window manually
                    logger.info("Browser window closed by user.")
                    break

            return False, "Manual login finished."
        finally:
            scraper.close_browser()
            scraper.release_lock()

"""
Base scraper engine with persistent browser lifecycle, locking, and pacing.
Follows rules in PRD §6.9, §7.2, and §13.
"""

import os
import sys
import time
import random
from pathlib import Path
from typing import Optional, Tuple, Any, Dict
from datetime import datetime, timezone
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class ScraperLockError(Exception):
    pass


class BaseScraper:
    def __init__(self, profile_label: str = "default"):
        self.profile_label = profile_label
        if profile_label in ("default", "indo", "main", "thailand") and settings.CHROME_USER_DATA_DIR and Path(settings.CHROME_USER_DATA_DIR).exists():
            self.profile_dir = Path(settings.CHROME_USER_DATA_DIR).resolve()
        else:
            self.profile_dir = settings.RUNTIME_DIR / "profiles" / "kalodata" / profile_label
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.lock_file_path = settings.RUNTIME_DIR / "locks" / f"profile_{profile_label}.lock"
        self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file_fd = None
        self.redis_client = None
        self.playwright = None
        self.browser_context = None

    def acquire_lock(self, timeout_sec: int = 10) -> bool:
        """
        Acquires file lock and optional Redis lock (§7.2).
        Single process per profile directory.
        """
        # 1. File lock
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            try:
                # Open or create lock file with strict permissions
                self.lock_file_fd = os.open(
                    self.lock_file_path,
                    os.O_CREAT | os.O_EXCL | os.O_RDWR
                )
                os.write(self.lock_file_fd, f"{os.getpid()}\n".encode("utf-8"))
                break
            except FileExistsError:
                # Check if holding process is still alive (§7.2 stale lock recovery)
                try:
                    if self.lock_file_path.exists():
                        pid_str = self.lock_file_path.read_text().strip()
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            is_alive = False
                            if sys.platform == "win32":
                                import ctypes
                                kernel32 = ctypes.windll.kernel32
                                h_proc = kernel32.OpenProcess(0x1000, False, pid)
                                if h_proc:
                                    exit_code = ctypes.c_ulong()
                                    kernel32.GetExitCodeProcess(h_proc, ctypes.byref(exit_code))
                                    kernel32.CloseHandle(h_proc)
                                    is_alive = (exit_code.value == 259)
                            else:
                                try:
                                    os.kill(pid, 0)
                                    is_alive = True
                                except OSError:
                                    is_alive = False
                            if not is_alive:
                                self.lock_file_path.unlink(missing_ok=True)
                                continue
                except Exception:
                    pass
                time.sleep(0.5)

        if self.lock_file_fd is None:
            raise ScraperLockError(f"Profile '{self.profile_label}' is currently locked by another process.")

        # 2. Redis lock (if available)
        try:
            import redis
            self.redis_client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=3)
            acquired = self.redis_client.set(
                f"lock:profile:{self.profile_label}",
                os.getpid(),
                ex=settings.JOB_TIMEOUT_MINUTES * 60,
                nx=True
            )
            if not acquired:
                self.release_lock()
                raise ScraperLockError(f"Redis lock: profile '{self.profile_label}' is busy.")
        except Exception as e:
            logger.warning("Redis lock unavailable, relying on filesystem lock", error=str(e))

        return True

    def release_lock(self):
        """Releases file lock and Redis lock."""
        if self.lock_file_fd is not None:
            try:
                os.close(self.lock_file_fd)
            except Exception:
                pass
            try:
                if self.lock_file_path.exists():
                    self.lock_file_path.unlink()
            except Exception:
                pass
            self.lock_file_fd = None

        if self.redis_client:
            try:
                self.redis_client.delete(f"lock:profile:{self.profile_label}")
            except Exception:
                pass
            self.redis_client = None

    def launch_browser(self, headless: Optional[bool] = None, slow_mo: int = 100, channel: Optional[str] = None):
        """
        Launches persistent browser context (§7.2, §7.6).
        Uses installed Google Chrome by default on Windows for seamless local testing.
        """
        from playwright.sync_api import sync_playwright

        if headless is None:
            headless = settings.KALODATA_HEADLESS

        if channel is None and sys.platform == "win32":
            channel = "chrome"

        env = os.environ.copy()
        if sys.platform != "win32" and settings.KALODATA_DISPLAY and not headless:
            env["DISPLAY"] = settings.KALODATA_DISPLAY

        self.playwright = sync_playwright().start()

        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ]

        logger.info(
            "Launching browser persistent context",
            profile_dir=str(self.profile_dir),
            headless=headless,
            channel=channel,
            display=env.get("DISPLAY")
        )

        kwargs = {
            "user_data_dir": str(self.profile_dir),
            "headless": headless,
            "slow_mo": slow_mo,
            "args": args,
            "viewport": {"width": 1440, "height": 900},
            "env": env,
        }
        if channel:
            kwargs["channel"] = channel

        try:
            self.browser_context = self.playwright.chromium.launch_persistent_context(**kwargs)
        except Exception as ex:
            err_msg = str(ex)
            # Fallback 1: If launched with channel (e.g. system chrome) and failed, try standard chromium
            if kwargs.get("channel"):
                logger.warning("Failed to launch with channel, falling back to default chromium", error=err_msg)
                kwargs.pop("channel", None)
                try:
                    self.browser_context = self.playwright.chromium.launch_persistent_context(**kwargs)
                except Exception as inner_ex:
                    ex = inner_ex
                    err_msg = str(inner_ex)

            # Fallback 2: If headed launch failed (e.g. missing XServer or $DISPLAY), fallback automatically to headless
            if self.browser_context is None and not kwargs.get("headless"):
                logger.warning(
                    "Headed browser launch failed (missing XServer or $DISPLAY). Falling back automatically to headless=True...",
                    error=err_msg
                )
                kwargs["headless"] = True
                kwargs.pop("channel", None)
                try:
                    self.browser_context = self.playwright.chromium.launch_persistent_context(**kwargs)
                except Exception as head_ex:
                    logger.error("Headless fallback also failed", error=str(head_ex))
                    raise head_ex
            elif self.browser_context is None:
                raise ex

        # Auto-import portable session cookies if kalodata_session.json exists
        session_file = settings.RUNTIME_DIR / "kalodata_session.json"
        if session_file.exists():
            try:
                import json
                with open(session_file, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                    cookies = state_data.get("cookies", [])
                    if cookies:
                        self.browser_context.add_cookies(cookies)
            except Exception as e:
                logger.debug("Auto cookie restore skipped or failed", error=str(e))

        return self.browser_context

    def close_browser(self):
        """Closes browser context and shuts down Playwright."""
        try:
            if self.browser_context:
                # Save session snapshot for seamless portability
                try:
                    session_file = settings.RUNTIME_DIR / "kalodata_session.json"
                    self.browser_context.storage_state(path=str(session_file))
                except Exception:
                    pass
                self.browser_context.close()
        except Exception as e:
            logger.warning("Error closing browser context", error=str(e))
        finally:
            self.browser_context = None

        try:
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.warning("Error stopping playwright", error=str(e))
        finally:
            self.playwright = None

    def take_screenshot(self, page, stage: str, job_id: Optional[str] = None) -> Path:
        """Takes diagnostic screenshot and saves to runtime/screenshots/."""
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix = f"{job_id}_" if job_id else ""
        filename = f"{prefix}{stage}_{timestamp_str}.png"
        target_path = settings.RUNTIME_DIR / "screenshots" / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(target_path), full_page=False)
            logger.info("Diagnostic screenshot saved", path=str(target_path))
        except Exception as e:
            logger.warning("Failed to take screenshot", error=str(e))
        return target_path

    @staticmethod
    def pacing_page_delay():
        """Random delay between page navigations (§6.9)."""
        delay = random.uniform(settings.DELAY_PAGE_MIN, settings.DELAY_PAGE_MAX)
        time.sleep(delay)

    @staticmethod
    def pacing_detail_delay():
        """Random delay between product detail navigations (§6.9)."""
        delay = random.uniform(settings.DELAY_DETAIL_MIN, settings.DELAY_DETAIL_MAX)
        time.sleep(delay)

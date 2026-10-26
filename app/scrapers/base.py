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
        # Priority 1: Check configured CHROME_USER_DATA_DIR
        if settings.CHROME_USER_DATA_DIR and Path(settings.CHROME_USER_DATA_DIR).exists():
            self.profile_dir = Path(settings.CHROME_USER_DATA_DIR).resolve()
        # Priority 2: Check runtime/chrome_profile
        elif (settings.RUNTIME_DIR / "chrome_profile").exists():
            self.profile_dir = (settings.RUNTIME_DIR / "chrome_profile").resolve()
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

    @classmethod
    def force_unlock(cls, profile_label: str = "indo"):
        """Cleans up stale lock file and Redis lock for a profile."""
        lock_file = settings.RUNTIME_DIR / "locks" / f"profile_{profile_label}.lock"
        try:
            if lock_file.exists():
                lock_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            import redis
            r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)
        # Clean Chrome Singleton locks across runtime profiles
        for base_p in [settings.RUNTIME_DIR / "chrome_profile", settings.RUNTIME_DIR / "profiles" / "kalodata" / profile_label]:
            for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                sf = base_p / lock_name
                try:
                    if sf.is_symlink() or sf.exists():
                        sf.unlink(missing_ok=True)
                except Exception:
                    pass

    def launch_browser(self, headless: Optional[bool] = None, slow_mo: int = 100, channel: Optional[str] = None):
        """
        Launches persistent browser context (§7.2, §7.6).
        Uses installed Google Chrome by default on Windows for seamless local testing.
        """
        from playwright.sync_api import sync_playwright

        if headless is None:
            headless = settings.KALODATA_HEADLESS

        if channel is None:
            raw_channel = os.getenv("CHROME_CHANNEL", "").strip()
            if raw_channel:
                channel = raw_channel
            elif sys.platform == "win32":
                channel = "chrome"
            else:
                channel = "chrome"

        env = os.environ.copy()
        if headless:
            env.pop("DISPLAY", None)
            env.pop("WAYLAND_DISPLAY", None)
        elif sys.platform != "win32" and settings.KALODATA_DISPLAY:
            env["DISPLAY"] = settings.KALODATA_DISPLAY

        self.playwright = sync_playwright().start()

        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if headless:
            args.extend([
                "--headless=new",
                "--disable-gpu",
            ])

        logger.info(
            "Launching browser persistent context",
            profile_dir=str(self.profile_dir),
            headless=headless,
            channel=channel,
            display=env.get("DISPLAY")
        )

        if sys.platform == "win32":
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        else:
            user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        kwargs = {
            "user_data_dir": str(self.profile_dir),
            "headless": headless,
            "slow_mo": slow_mo,
            "args": args,
            "viewport": {"width": 1440, "height": 900},
            "user_agent": user_agent,
            "env": env,
        }
        if channel:
            kwargs["channel"] = channel

        # Clean stale Chrome Singleton locks from previous container crashes/restarts
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            singleton_file = self.profile_dir / lock_name
            try:
                if singleton_file.is_symlink() or singleton_file.exists():
                    singleton_file.unlink(missing_ok=True)
            except Exception:
                pass

        try:
            self.browser_context = self.playwright.chromium.launch_persistent_context(**kwargs)
        except Exception as ex:
            err_msg = str(ex)
            # Fallback: If launched with channel (e.g. system chrome) and failed, try standard bundled chromium
            if kwargs.get("channel"):
                logger.warning("Failed to launch with channel, falling back to default chromium", error=err_msg)
                kwargs.pop("channel", None)
                self.browser_context = self.playwright.chromium.launch_persistent_context(**kwargs)
            else:
                raise ex

        # Stealth init script: ensure webdriver is clean and realistic browser properties exist
        try:
            self.browser_context.add_init_script("""
                try {
                    if (navigator.hasOwnProperty('webdriver')) {
                        delete navigator.webdriver;
                    }
                    const proto = Object.getPrototypeOf(navigator);
                    if (proto && 'webdriver' in proto) {
                        Object.defineProperty(proto, 'webdriver', {
                            get: () => false,
                            configurable: true,
                            enumerable: true
                        });
                    }
                } catch (e) {}

                try {
                    if (!window.chrome) {
                        window.chrome = {
                            app: {
                                isInstalled: false,
                                InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                                RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
                            },
                            csi: function() {},
                            loadTimes: function() {},
                            runtime: {}
                        };
                    }
                } catch (e) {}

                try {
                    if (navigator.plugins && navigator.plugins.length === 0) {
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5],
                            enumerable: true,
                            configurable: true
                        });
                    }
                } catch (e) {}
            """)
        except Exception:
            pass

        # Auto-import portable session cookies & localStorage if kalodata_session.json exists
        session_file = settings.RUNTIME_DIR / "kalodata_session.json"
        if session_file.exists():
            try:
                import json
                with open(session_file, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                    cookies = state_data.get("cookies", [])
                    if cookies:
                        self.browser_context.add_cookies(cookies)

                    # Pre-load localStorage for Kalodata origin
                    origins = state_data.get("origins", [])
                    for orig in origins:
                        origin_url = orig.get("origin", "")
                        storage_items = orig.get("localStorage", [])
                        if "kalodata.com" in origin_url and storage_items:
                            storage_js = ",\n".join(
                                f"{json.dumps(it['name'])}: {json.dumps(it['value'])}"
                                for it in storage_items
                            )
                            self.browser_context.add_init_script(f"""
                                try {{
                                    if (location.origin.includes('kalodata.com')) {{
                                        const stored = {{{storage_js}}};
                                        for (const [k, v] of Object.entries(stored)) {{
                                            if (!localStorage.getItem(k)) {{
                                                localStorage.setItem(k, v);
                                            }}
                                        }}
                                    }}
                                }} catch (e) {{}}
                            """)
            except Exception as e:
                logger.debug("Auto session restore skipped or failed", error=str(e))

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

    @staticmethod
    def is_challenge_active(page) -> bool:
        """
        Detects if Cloudflare Turnstile, CAPTCHA, or challenge page is present.
        """
        try:
            raw_title = page.title()
            if isinstance(raw_title, str):
                page_title = raw_title.lower()
                if any(term in page_title for term in ["just a moment", "attention required", "cloudflare"]):
                    return True
        except Exception:
            pass

        try:
            loc = page.locator("iframe[src*='challenges.cloudflare.com'], iframe[title*='Cloudflare'], #challenge-stage, #cf-turnstile")
            vis = loc.first.is_visible(timeout=300)
            if vis is True:
                return True
        except Exception:
            pass

        try:
            loc2 = page.locator("text=/Verify you are human|Verifikasi bahwa Anda manusia|Verify to continue|Checking your browser/i")
            vis2 = loc2.first.is_visible(timeout=300)
            if vis2 is True:
                return True
        except Exception:
            pass

        try:
            frames = getattr(page, "frames", None)
            if isinstance(frames, (list, tuple)):
                for frame in frames:
                    f_url = getattr(frame, "url", None)
                    if isinstance(f_url, str) and ("challenges.cloudflare.com" in f_url.lower() or "turnstile" in f_url.lower()):
                        return True
        except Exception:
            pass

        return False

    @classmethod
    def wait_for_challenge(
        cls,
        page,
        job_id: Optional[str] = None,
        max_wait_sec: int = 180,
        cancel_check_cb=None
    ) -> Tuple[bool, str]:
        """
        Human-in-the-loop solver for Cloudflare Turnstile / CAPTCHA (§7.4).
        If challenge is detected, sets job status to BLOCKED and pauses execution.
        The operator can view the browser in VNC Viewer (port 5902) and click the checkbox manually.
        Once resolved, restores job status to RUNNING.
        """
        if not cls.is_challenge_active(page):
            return True, "NONE"

        logger.warning(
            "Cloudflare challenge detected! Pausing job for manual VNC interaction",
            job_id=job_id,
            vnc_port=5902,
            timeout_sec=max_wait_sec
        )

        from app.services.job_service import JobService
        if job_id:
            JobService.set_job_status(
                job_id=job_id,
                status="BLOCKED",
                error_summary="Cloudflare Turnstile terdeteksi. Silakan buka VNC Viewer (Port 5902) dan klik kotak verifikasi."
            )

        start_time = time.time()
        while time.time() - start_time < max_wait_sec:
            if cancel_check_cb and cancel_check_cb():
                logger.info("Scrape job cancelled by operator while waiting for VNC challenge click", job_id=job_id)
                return False, "CANCELLED"

            time.sleep(3)

            if not cls.is_challenge_active(page):
                logger.info("Cloudflare challenge cleared! Resuming scrape job...", job_id=job_id)
                if job_id:
                    JobService.set_job_status(
                        job_id=job_id,
                        status="RUNNING",
                        error_summary=None
                    )
                time.sleep(2)
                return True, "RESOLVED"

        logger.error("Timed out waiting for manual Cloudflare resolution in VNC", job_id=job_id)
        if job_id:
            JobService.set_job_status(
                job_id=job_id,
                status="FAILED",
                error_summary="Batas waktu habis (3 menit) menunggu verifikasi Turnstile di VNC Viewer."
            )
        return False, "TIMEOUT"

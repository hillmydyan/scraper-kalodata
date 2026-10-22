"""
Configuration loader for Kalodata Scraper & Dashboard.
Loads environment variables (.env) and YAML configurations from config/ directory.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

# Load .env file
load_dotenv(BASE_DIR / ".env")


def load_yaml(filename: str) -> Dict[str, Any]:
    file_path = CONFIG_DIR / filename
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# Load static configurations
APP_CONFIG = load_yaml("app.yaml")
COUNTRIES_CONFIG = load_yaml("countries.yaml")
FILTERS_CONFIG = load_yaml("filters.yaml")
SELECTORS_CONFIG = load_yaml("selectors.yaml").get("selectors", {})
NUMBER_FORMATS_CONFIG = load_yaml("number_formats.yaml").get("number_formats", {})


class Settings:
    # Environment
    APP_ENV: str = os.getenv("APP_ENV", "production")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-dev-secret-key-change-in-prod")
    
    # Databases
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://kalodata:kalodata_password@127.0.0.1:5433/kalodata"
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6380/0")
    
    # Timezone & Kalodata
    TZ: str = os.getenv("TZ", APP_CONFIG.get("app", {}).get("timezone", "Asia/Jakarta"))
    KALODATA_BASE_URL: str = os.getenv("KALODATA_BASE_URL", "https://www.kalodata.com")
    KALODATA_UI_LANGUAGE: str = os.getenv(
        "KALODATA_UI_LANGUAGE",
        APP_CONFIG.get("app", {}).get("kalodata_ui_language", "en")
    )
    
    # Browser & Display
    KALODATA_DISPLAY: str = os.getenv("KALODATA_DISPLAY", ":1")
    KALODATA_HEADLESS: bool = os.getenv("KALODATA_HEADLESS", "true" if sys.platform != "win32" else "false").lower() == "true"
    _raw_chrome_dir = os.getenv("CHROME_USER_DATA_DIR", "runtime/chrome_profile")
    CHROME_USER_DATA_DIR: str = str((BASE_DIR / _raw_chrome_dir).resolve()) if not Path(_raw_chrome_dir).is_absolute() else _raw_chrome_dir
    
    # Storage & Runtime
    RUNTIME_DIR: Path = Path(os.getenv("RUNTIME_DIR", str(BASE_DIR / "runtime"))).resolve()
    WEB_PORT: int = int(os.getenv("WEB_PORT", "8081"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL")

    # Scraper & scheduler params
    MAX_PRODUCTS_PER_COUNTRY: int = APP_CONFIG.get("scraping", {}).get("max_products_per_country", 2000)
    MIN_CREATOR_REVENUE_IDR: float = float(APP_CONFIG.get("scraping", {}).get("min_creator_revenue_idr", 4000000))
    MIN_PRODUCT_SALES: int = int(APP_CONFIG.get("scraping", {}).get("min_product_sales", 50))
    CHECKPOINT_EVERY: int = APP_CONFIG.get("scraping", {}).get("checkpoint_every", 25)
    MAX_REJECT_RATIO: float = APP_CONFIG.get("scraping", {}).get("max_reject_ratio", 0.20)
    DELAY_PAGE_MIN: float = APP_CONFIG.get("scraping", {}).get("delay_page_min_sec", 2.0)
    DELAY_PAGE_MAX: float = APP_CONFIG.get("scraping", {}).get("delay_page_max_sec", 5.0)
    DELAY_DETAIL_MIN: float = APP_CONFIG.get("scraping", {}).get("delay_detail_min_sec", 1.5)
    DELAY_DETAIL_MAX: float = APP_CONFIG.get("scraping", {}).get("delay_detail_max_sec", 4.0)
    JOB_TIMEOUT_MINUTES: int = APP_CONFIG.get("scraping", {}).get("job_timeout_minutes", 90)
    DAILY_RUN_TIMEOUT_MINUTES: int = APP_CONFIG.get("scraping", {}).get("daily_run_timeout_minutes", 300)
    MAX_VIDEOS_SCANNED: int = APP_CONFIG.get("scraping", {}).get("max_videos_scanned", 50)
    
    # Readiness
    READINESS_RETRY_MINUTES: int = APP_CONFIG.get("readiness", {}).get("retry_minutes", 60)
    READINESS_DEADLINE_HOUR_WIB: int = APP_CONFIG.get("readiness", {}).get("deadline_hour_wib", 10)
    
    # Retention
    RETENTION_EXCEL_DAYS: int = APP_CONFIG.get("retention", {}).get("excel_days", 5)
    RETENTION_SCREENSHOT_DAYS: int = APP_CONFIG.get("retention", {}).get("screenshot_days", 30)
    RETENTION_LOG_DAYS: int = APP_CONFIG.get("retention", {}).get("log_days", 30)
    RETENTION_AUDIT_DAYS: int = APP_CONFIG.get("retention", {}).get("audit_days", 365)
    EXPORT_EMPTY_FILE: bool = APP_CONFIG.get("export", {}).get("export_empty_file", False)
    MIN_FREE_DISK_MB: int = APP_CONFIG.get("app", {}).get("min_free_disk_mb", 2000)


settings = Settings()

# Ensure runtime directories exist
def init_runtime_dirs():
    subdirs = [
        "profiles/kalodata",
        "exports",
        "logs",
        "screenshots",
        "locks"
    ]
    for sub in subdirs:
        p = settings.RUNTIME_DIR / sub
        p.mkdir(parents=True, exist_ok=True)


def sel(name: str) -> Dict[str, Any]:
    """
    Get selector configuration by name (§13.4).
    Returns dict: {primary: str, fallbacks: List[str], kind: str}
    """
    if name not in SELECTORS_CONFIG:
        raise KeyError(f"Selector '{name}' is not defined in config/selectors.yaml")
    return SELECTORS_CONFIG[name]


def get_country_config(country_code: str) -> Dict[str, Any]:
    """Get country settings from countries.yaml"""
    countries = COUNTRIES_CONFIG.get("countries", {})
    if country_code not in countries:
        raise ValueError(f"Country code '{country_code}' not found in countries.yaml")
    return countries[country_code]

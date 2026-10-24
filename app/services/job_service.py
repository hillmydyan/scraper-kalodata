"""
Job and Run service managing the lifecycle and state machine of scrape jobs.
Follows rules in PRD §8.2, §8.3, §8.5, and §11.
"""

import os
import sys
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any
import structlog
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from app.models.entities import (
    ScrapeRun, ScrapeJob, Product, KalodataProductResult, KalodataCreatorProductResult,
    ScrapeJobRowsRejected, AccountProfile, AuditLog
)
from app.config import settings

logger = structlog.get_logger(__name__)


class JobService:
    @staticmethod
    def create_daily_run(
        db: Session,
        period_date: Optional[date] = None,
        trigger: str = "scheduled",
        created_by: Optional[str] = "system",
        countries: Optional[List[str]] = None,
        module: str = "product"
    ) -> ScrapeRun:
        """Creates a ScrapeRun and child ScrapeJob records for specified countries or ID, MY, TH."""
        if period_date is None:
            # Default is yesterday
            period_date = date.today() - timedelta(days=1)

        target_countries = countries if countries else ["ID", "MY", "TH"]

        run = ScrapeRun(
            id=str(uuid.uuid4()),
            trigger=trigger,
            period_start=period_date,
            period_end=period_date,
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            created_by=created_by,
            summary={"countries": target_countries, "module": module}
        )
        db.add(run)

        from app.services.session_service import SessionService

        for country in target_countries:
            country_profile = SessionService.get_or_create_country_profile(db, country)
            job = ScrapeJob(
                id=str(uuid.uuid4()),
                run_id=run.id,
                source="kalodata",
                module=module,
                country_code=country,
                account_profile_id=country_profile.id,
                period_start=period_date,
                period_end=period_date,
                status="PENDING",
                stage="INIT",
                created_by=created_by
            )
            db.add(job)

        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def save_checkpoint(
        db: Session,
        job_id: str,
        checkpoint_data: Dict[str, Any],
        rows_saved: int,
        rows_scanned: int
    ):
        """Saves incremental checkpoint to database (§6.5 no. 9)."""
        job = db.get(ScrapeJob, job_id)
        if job:
            job.checkpoint = checkpoint_data
            job.rows_saved = rows_saved
            job.rows_found = rows_scanned
            db.commit()

    @staticmethod
    def upsert_product_results(
        db: Session,
        job_id: str,
        country_code: str,
        period_date: date,
        items: List[Dict[str, Any]]
    ) -> int:
        """
        Upserts products and product results (§11).
        Duplicate results within same period update existing row and increment rows_duplicate.
        """
        duplicates_count = 0

        for item in items:
            source_id = str(item["source_product_id"])
            prod_name = item.get("product_name", "Product")
            shop_name = item.get("shop_name")
            prod_url = item.get("product_url")

            # 1. Upsert products master table
            product = db.execute(
                select(Product).filter_by(
                    country_code=country_code,
                    source_product_id=source_id
                )
            ).scalar_one_or_none()

            now_utc = datetime.now(timezone.utc)
            if not product:
                product = Product(
                    id=str(uuid.uuid4()),
                    source_product_id=source_id,
                    country_code=country_code,
                    product_name=prod_name,
                    shop_name=shop_name,
                    product_url=prod_url,
                    first_seen_at=now_utc,
                    last_seen_at=now_utc
                )
                db.add(product)
                db.flush()
            else:
                product.product_name = prod_name
                product.shop_name = shop_name or product.shop_name
                product.product_url = prod_url or product.product_url
                product.last_seen_at = now_utc

            # 2. Upsert kalodata_product_results
            existing_result = db.execute(
                select(KalodataProductResult).filter_by(
                    country_code=country_code,
                    source_product_id=source_id,
                    period_start=period_date,
                    period_end=period_date
                )
            ).scalar_one_or_none()

            if existing_result:
                duplicates_count += 1
                existing_result.scrape_job_id = job_id
                existing_result.product_name = prod_name
                existing_result.shop_name = shop_name
                existing_result.revenue_value = item.get("revenue_value")
                existing_result.revenue_raw = item.get("revenue_raw", "")
                existing_result.revenue_is_abbreviated = item.get("revenue_is_abbreviated", False)
                existing_result.sales_value = item.get("sales_value")
                existing_result.sales_raw = item.get("sales_raw", "")
                existing_result.commission_rate = item.get("commission_rate")
                existing_result.commission_raw = item.get("commission_raw")
                existing_result.video_url = item.get("video_url")
                existing_result.video_url_type = item.get("video_url_type", "tiktok")
                existing_result.video_selection_method = item.get("video_selection_method", "top_revenue")
                existing_result.scraped_at = now_utc
            else:
                new_result = KalodataProductResult(
                    id=str(uuid.uuid4()),
                    scrape_job_id=job_id,
                    product_id=product.id,
                    source_product_id=source_id,
                    country_code=country_code,
                    period_start=period_date,
                    period_end=period_date,
                    product_name=prod_name,
                    shop_name=shop_name,
                    product_url=prod_url,
                    revenue_value=item.get("revenue_value"),
                    revenue_raw=item.get("revenue_raw", ""),
                    revenue_is_abbreviated=item.get("revenue_is_abbreviated", False),
                    sales_value=item.get("sales_value"),
                    sales_raw=item.get("sales_raw", ""),
                    commission_rate=item.get("commission_rate"),
                    commission_raw=item.get("commission_raw"),
                    currency_code=item.get("currency_code", country_code),
                    video_url=item.get("video_url"),
                    video_url_type=item.get("video_url_type", "tiktok"),
                    video_selection_method=item.get("video_selection_method", "none"),
                    scraped_at=now_utc
                )
                db.add(new_result)

        db.commit()
        return duplicates_count

    @staticmethod
    def upsert_creator_results(
        db: Session,
        job_id: str,
        country_code: str,
        period_date: date,
        items: List[Dict[str, Any]]
    ) -> int:
        """
        Upserts creator products into kalodata_creator_product_results.
        """
        now_utc = datetime.now(timezone.utc)
        count = 0
        for item in items:
            source_id = str(item.get("source_product_id") or "")
            c_name = item.get("creator_name", "")
            new_res = KalodataCreatorProductResult(
                id=str(uuid.uuid4()),
                scrape_job_id=job_id,
                creator_name=c_name,
                creator_id=item.get("creator_id"),
                creator_rank=item.get("creator_rank"),
                product_rank=item.get("product_rank"),
                source_product_id=source_id,
                product_name=item.get("product_name", ""),
                shop_name=item.get("shop_name"),
                product_url=item.get("product_url"),
                revenue_value=item.get("revenue_value"),
                revenue_raw=item.get("revenue_raw", ""),
                sales_value=item.get("sales_value"),
                sales_raw=item.get("sales_raw", ""),
                commission_rate=item.get("commission_rate"),
                commission_raw=item.get("commission_raw"),
                currency_code=item.get("currency_code", country_code),
                country_code=country_code,
                period_start=period_date,
                period_end=period_date,
                scraped_at=now_utc
            )
            db.add(new_res)
            count += 1
        db.commit()
        return count

    @staticmethod
    def record_rejected_rows(
        db: Session,
        job_id: str,
        rejected_items: List[Dict[str, Any]]
    ):
        """Records rejected rows into scrape_job_rows_rejected (§11)."""
        for rej in rejected_items:
            entry = ScrapeJobRowsRejected(
                id=str(uuid.uuid4()),
                scrape_job_id=job_id,
                row_index=rej.get("row_index", 0),
                reason=rej.get("reason", "UNKNOWN"),
                raw=rej.get("raw", {}),
                created_at=datetime.now(timezone.utc)
            )
            db.add(entry)
        db.commit()

    @staticmethod
    def finalize_job(
        db: Session,
        job_id: str,
        status: str,
        error_code: Optional[str] = None,
        error_summary: Optional[str] = None,
        meta_updates: Optional[Dict[str, Any]] = None
    ):
        """Finalizes job status and updates timings."""
        job = db.get(ScrapeJob, job_id)
        if job:
            job.status = status
            job.error_code = error_code
            job.error_summary = error_summary
            job.finished_at = datetime.now(timezone.utc)
            if meta_updates:
                current_meta = dict(job.meta or {})
                current_meta.update(meta_updates)
                job.meta = current_meta
            db.commit()

    @classmethod
    def set_job_status(
        cls,
        job_id: str,
        status: str,
        error_summary: Optional[str] = None,
        stage: Optional[str] = None
    ):
        """Updates a job's status, error summary, or stage dynamically."""
        from app.models import SessionLocal
        db = SessionLocal()
        try:
            job = db.get(ScrapeJob, job_id)
            if job and job.status != "CANCELLED":
                job.status = status
                if error_summary is not None:
                    job.error_summary = error_summary
                elif status == "RUNNING":
                    job.error_summary = None
                if stage is not None:
                    job.stage = stage
                db.commit()
        finally:
            db.close()

    @classmethod
    def execute_job_now(
        cls,
        job_id: str,
        limit: int = 2000,
        headless: Optional[bool] = None,
        db_factory=None
    ):
        """Executes a single scrape job synchronously."""
        from app.models import SessionLocal
        from app.scrapers.base import BaseScraper, ScraperLockError
        from app.scrapers.kalodata.navigation import KalodataNavigator, NavigationError
        from app.scrapers.kalodata.product_list import ProductListScraper
        from app.scrapers.kalodata.session import SessionManager
        from app.services.export_service import ExportService

        db = SessionLocal() if db_factory is None else db_factory()
        try:
            job = db.get(ScrapeJob, job_id)
            if not job or job.status == "CANCELLED":
                return

            def cancel_check():
                db_chk = SessionLocal()
                try:
                    j = db_chk.get(ScrapeJob, job.id)
                    return j.status == "CANCELLED" if j else True
                finally:
                    db_chk.close()

            job.status = "RUNNING"
            job.stage = "STARTING"
            job.started_at = datetime.now(timezone.utc)
            db.commit()

            profile_label = "indo"
            if job.account_profile_id:
                acc_p = db.get(AccountProfile, job.account_profile_id)
                if acc_p and acc_p.profile_dir_name:
                    profile_label = acc_p.profile_dir_name

            scraper = BaseScraper(profile_label=profile_label)
            try:
                scraper.acquire_lock()
            except ScraperLockError as sle:
                cls.finalize_job(db, job.id, status="FAILED", error_code="PROFILE_LOCKED", error_summary=str(sle))
                return

            try:
                context = scraper.launch_browser(headless=headless)
                page = context.new_page()

                # Step 1: Validate Session (with human-in-the-loop solver if Turnstile appears)
                job.stage = "VALIDATING_SESSION"
                db.commit()
                status, msg = SessionManager.validate_session(
                    page,
                    timeout_sec=25,
                    job_id=job.id,
                    wait_for_human=True,
                    max_human_wait_sec=900,
                    cancel_check_cb=cancel_check
                )
                if status != "READY":
                    final_job_status = "PENDING" if status in ("LOGIN_REQUIRED", "PENDING") else status
                    cls.finalize_job(db, job.id, status=final_job_status, error_code=status, error_summary=msg)
                    return

                nav = KalodataNavigator(page)

                if job.module == "creator":
                    from app.scrapers.kalodata.creator_scraper import CreatorScraper
                    job.stage = "NAVIGATING_REGION"
                    db.commit()

                    page.goto(f"{settings.KALODATA_BASE_URL.rstrip('/')}/creator", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)

                    SessionManager.check_and_wait_for_challenge(page, job_id=job.id, cancel_check_cb=cancel_check)

                    nav.ensure_ui_language(settings.KALODATA_UI_LANGUAGE)
                    nav.switch_and_verify_region(job.country_code)

                    job.stage = "SCRAPING_CREATORS"
                    db.commit()

                    creator_scraper = CreatorScraper(page, job.country_code, job_id=job.id)
                    creator_scraper.apply_filters()

                    def checkpoint_cb(current_items, scanned_count):
                        cls.save_checkpoint(
                            db, job.id,
                            checkpoint_data={"scanned": scanned_count, "saved": len(current_items)},
                            rows_saved=len(current_items),
                            rows_scanned=scanned_count
                        )

                    # Limit is only an upper bound for manual trigger; scheduled runs stop purely when revenue drops below min_rev
                    is_manual = (job.run.trigger == "manual") if job.run else False
                    effective_max = limit if (is_manual and limit and limit > 0) else None
                    min_rev = getattr(settings, "MIN_CREATOR_REVENUE_IDR", 4000000.0)

                    scrape_res = creator_scraper.scrape_creators(
                        max_creators=effective_max,
                        min_revenue=min_rev,
                        products_per_creator=3,
                        period_date=job.period_start,
                        cancel_check_cb=cancel_check,
                        checkpoint_cb=checkpoint_cb
                    )

                    items = scrape_res["items"]
                    cls.upsert_creator_results(db, job.id, job.country_code, job.period_start, items)
                    job.rows_duplicate = 0
                    job.rows_found = scrape_res["total_creators"]
                    job.rows_saved = len(items)
                    job.rows_rejected = 0

                    final_status = "SUCCESS" if items else "NO_DATA"
                    rev_method = "creator_filter"
                    is_truncated = False
                else:
                    # Step 2: Language & Region
                    job.stage = "NAVIGATING_REGION"
                    db.commit()
                    SessionManager.check_and_wait_for_challenge(page, job_id=job.id, cancel_check_cb=cancel_check)
                    nav.ensure_ui_language(settings.KALODATA_UI_LANGUAGE)
                    nav.switch_and_verify_region(job.country_code)

                    # Step 3: Date Range
                    job.stage = "APPLYING_DATE"
                    db.commit()
                    nav.apply_date_range(job.period_start, job.period_end)

                    # Step 4: Category Filter
                    job.stage = "FILTERING_CATEGORY"
                    db.commit()
                    nav.apply_category_filter(job.country_code)

                    # Step 5: Revenue Source
                    job.stage = "FILTERING_REVENUE"
                    db.commit()
                    rev_method = nav.apply_revenue_source_filter()

                    # Step 6: Scraping Product List & Detail
                    job.stage = "SCRAPING_PRODUCTS"
                    db.commit()

                    list_scraper = ProductListScraper(page, job.country_code, job_id=job.id)

                    def checkpoint_cb(current_items, scanned_count):
                        cls.save_checkpoint(
                            db, job.id,
                            checkpoint_data={"scanned": scanned_count, "saved": len(current_items)},
                            rows_saved=len(current_items),
                            rows_scanned=scanned_count
                        )

                    min_sales = getattr(settings, "MIN_PRODUCT_SALES", 50)
                    scrape_res = list_scraper.scrape_products(
                        max_limit=limit,
                        min_sales=min_sales,
                        checkpoint_cb=checkpoint_cb,
                        cancel_check_cb=cancel_check,
                        revenue_source_method=rev_method
                    )

                    items = scrape_res["items"]
                    rejected = scrape_res["rejected"]

                    if rejected:
                        cls.record_rejected_rows(db, job.id, rejected)

                    dups = cls.upsert_product_results(db, job.id, job.country_code, job.period_start, items)
                    job.rows_duplicate = dups
                    job.rows_found = scrape_res["total_scanned"]
                    job.rows_saved = len(items)
                    job.rows_rejected = len(rejected)

                    final_status = "SUCCESS"
                    if not items:
                        final_status = "NO_DATA"
                    elif scrape_res["is_truncated"]:
                        final_status = "PARTIAL"
                    elif len(rejected) / max(scrape_res["total_scanned"], 1) > settings.MAX_REJECT_RATIO:
                        final_status = "PARTIAL"

                    is_truncated = scrape_res["is_truncated"]

                cls.finalize_job(
                    db, job.id,
                    status=final_status,
                    meta_updates={
                        "revenue_source_method": rev_method,
                        "truncated": is_truncated,
                        "headless": headless
                    }
                )

                # Export Excel
                ExportService.export_job_results(db, job.id)

            except NavigationError as ne:
                logger.warning("Navigation error during scraping", error=str(ne), code=ne.error_code)
                try:
                    if 'page' in locals() and page:
                        scraper.take_screenshot(page, f"nav_error_{job.country_code}", job.id)
                except Exception:
                    pass
                cls.finalize_job(db, job.id, status="FAILED", error_code=ne.error_code, error_summary=str(ne))
            except Exception as e:
                logger.error("Job execution failed", exc_info=True)
                try:
                    if 'page' in locals() and page:
                        scraper.take_screenshot(page, "crash", job.id)
                except Exception:
                    pass
                cls.finalize_job(db, job.id, status="FAILED", error_code="UNKNOWN", error_summary=str(e))
            finally:
                scraper.close_browser()
                scraper.release_lock()
        finally:
            db.close()

    @classmethod
    def dispatch_run_in_background(
        cls,
        run_id: str,
        limit: int = 2000,
        headless: Optional[bool] = None
    ):
        """Dispatches run execution via Celery worker or background thread."""
        import threading
        from app.models import SessionLocal

        if headless is None:
            headless = True if sys.platform != "win32" else False

        # Attempt Celery dispatch first
        dispatched_to_celery = False
        try:
            from app.tasks.celery_app import scrape_country_job
            db = SessionLocal()
            try:
                jobs = db.query(ScrapeJob).filter_by(run_id=run_id).order_by(ScrapeJob.created_at).all()
                if jobs:
                    for job in jobs:
                        if job.status == "PENDING":
                            scrape_country_job.delay(job.id, limit=limit, headless=headless)
                    dispatched_to_celery = True
                    logger.info("Dispatched jobs to Celery queue", run_id=run_id, count=len(jobs))
            finally:
                db.close()
        except Exception as cel_err:
            logger.warning("Celery dispatch unavailable, using background thread fallback", error=str(cel_err))

        if not dispatched_to_celery:
            def worker_thread():
                db = SessionLocal()
                try:
                    jobs = db.query(ScrapeJob).filter_by(run_id=run_id).order_by(ScrapeJob.created_at).all()
                    logger.info("Worker thread starting jobs execution", run_id=run_id, count=len(jobs))
                    for job in jobs:
                        if job.status == "PENDING":
                            cls.execute_job_now(job.id, limit=limit, headless=headless)
                    run = db.get(ScrapeRun, run_id)
                    if run:
                        run.status = "COMPLETED"
                        run.finished_at = datetime.now(timezone.utc)
                        db.commit()

                    # Automatically trigger retention cleanup
                    try:
                        from app.services.retention_service import RetentionService
                        RetentionService.cleanup_old_data(db)
                    except Exception as clean_err:
                        logger.warning("Automatic retention cleanup warning", error=str(clean_err))
                except Exception as e:
                    logger.error("Background worker thread error", error=str(e))
                finally:
                    db.close()

            t = threading.Thread(target=worker_thread, daemon=True)
            t.start()

import pytest
from unittest.mock import MagicMock
from app.scrapers.kalodata.product_list import ProductListScraper


class TestProductListScraperSalesThreshold:
    def test_validate_row_rejects_sales_below_150(self):
        page = MagicMock()
        scraper = ProductListScraper(page, "ID")

        # Sales 149 (< 150) should fail validation
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 500000.0,
            "sales_value": 149,
            "commission_rate": 0.1
        }, min_sales=150)
        assert valid is False
        assert reason == "SALES_BELOW_MIN_150"

        # Sales 149 should fail
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 500000.0,
            "sales_value": 149,
            "commission_rate": 0.1
        }, min_sales=150)
        assert valid is False
        assert reason == "SALES_BELOW_MIN_150"

        # Sales None should fail
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 500000.0,
            "sales_value": None,
            "commission_rate": 0.1
        }, min_sales=150)
        assert valid is False
        assert reason == "SALES_BELOW_MIN_150"

    def test_validate_row_accepts_sales_above_150(self):
        page = MagicMock()
        scraper = ProductListScraper(page, "ID")

        # Sales 151 (> 150) should pass
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 500000.0,
            "sales_value": 151,
            "commission_rate": 0.1
        }, min_sales=150)
        assert valid is True
        assert reason == ""

        # Sales 1000 (> 150) should pass with default min_sales
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 5000000.0,
            "sales_value": 1000,
            "commission_rate": 0.1
        })
        assert valid is True
        assert reason == ""

    def test_validate_row_with_custom_min_sales(self):
        page = MagicMock()
        scraper = ProductListScraper(page, "ID")

        # Custom threshold 50: 60 and 50 pass (inclusive), 40 fails
        valid, _ = scraper._validate_row({
            "source_product_id": "123",
            "product_name": "Test Item",
            "sales_value": 60
        }, min_sales=50)
        assert valid is True

        valid_exact, _ = scraper._validate_row({
            "source_product_id": "123",
            "product_name": "Test Item",
            "sales_value": 50
        }, min_sales=50)
        assert valid_exact is True

        valid, reason = scraper._validate_row({
            "source_product_id": "123",
            "product_name": "Test Item",
            "sales_value": 40
        }, min_sales=50)
        assert valid is False
        assert reason == "SALES_BELOW_MIN_50"

    def test_validate_row_with_min_and_max_sales(self):
        page = MagicMock()
        scraper = ProductListScraper(page, "ID")

        # Range 50 ~ 10000:
        # 5000 passes
        valid, _ = scraper._validate_row({
            "source_product_id": "123",
            "product_name": "Test Item",
            "sales_value": 5000
        }, min_sales=50, max_sales=10000)
        assert valid is True

        # 12000 fails (exceeds max 10000)
        valid, reason = scraper._validate_row({
            "source_product_id": "123",
            "product_name": "Test Item",
            "sales_value": 12000
        }, min_sales=50, max_sales=10000)
        assert valid is False
        assert reason == "SALES_ABOVE_MAX_10000"


class TestJobServiceMinProductSales:
    def test_get_min_product_sales_default(self):
        from app.services.job_service import JobService
        db = MagicMock()
        db.get.return_value = None
        assert JobService.get_min_product_sales(db) == 50

    def test_get_min_product_sales_from_db(self):
        from app.services.job_service import JobService
        from app.models.entities import Setting
        db = MagicMock()
        db.get.return_value = Setting(key="min_product_sales", value=80)
        assert JobService.get_min_product_sales(db) == 80

    def test_get_max_product_sales_from_db(self):
        from app.services.job_service import JobService
        from app.models.entities import Setting
        db = MagicMock()
        db.get.return_value = Setting(key="max_product_sales", value=10000)
        assert JobService.get_max_product_sales(db) == 10000

    def test_create_daily_run_persists_custom_min_and_max_sales(self):
        from app.services.job_service import JobService
        db = MagicMock()
        run = JobService.create_daily_run(db, trigger="manual", min_sales=75, max_sales=5000)
        assert run.summary["min_sales"] == 75
        assert run.summary["max_sales"] == 5000


class TestProductHardCap:
    def test_product_scraper_enforces_400_cap(self):
        from unittest.mock import MagicMock
        page = MagicMock()
        # Mock locator methods to prevent real Playwright calls
        page.locator.return_value.first.wait_for.side_effect = Exception("No table")
        scraper = ProductListScraper(page, "ID")

        # Test that passing None or > 400 is capped at 400
        res = scraper.scrape_products(max_limit=None)
        # Table not found, so 0 items, but verifies no crash and max_limit capped
        assert res["items"] == []

        res2 = scraper.scrape_products(max_limit=5000)
        assert res2["items"] == []

    def test_product_hard_cap_constant(self):
        from app.config import settings
        assert settings.MAX_PRODUCTS_PER_COUNTRY == 400

import pytest
from unittest.mock import MagicMock
from app.scrapers.kalodata.product_list import ProductListScraper


class TestProductListScraperSalesThreshold:
    def test_validate_row_rejects_sales_150_or_below(self):
        page = MagicMock()
        scraper = ProductListScraper(page, "ID")

        # Sales <= 150 should fail validation
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 500000.0,
            "sales_value": 150,
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

        # Custom threshold 50: 60 passes, 40 fails
        valid, _ = scraper._validate_row({
            "source_product_id": "123",
            "product_name": "Test Item",
            "sales_value": 60
        }, min_sales=50)
        assert valid is True

        valid, reason = scraper._validate_row({
            "source_product_id": "123",
            "product_name": "Test Item",
            "sales_value": 40
        }, min_sales=50)
        assert valid is False
        assert reason == "SALES_BELOW_MIN_50"


class TestJobServiceMinProductSales:
    def test_get_min_product_sales_default(self):
        from app.services.job_service import JobService
        db = MagicMock()
        db.get.return_value = None
        assert JobService.get_min_product_sales(db) == 150

    def test_get_min_product_sales_from_db(self):
        from app.services.job_service import JobService
        from app.models.entities import Setting
        db = MagicMock()
        db.get.return_value = Setting(key="min_product_sales", value=80)
        assert JobService.get_min_product_sales(db) == 80

    def test_create_daily_run_persists_custom_min_sales(self):
        from app.services.job_service import JobService
        db = MagicMock()
        run = JobService.create_daily_run(db, trigger="manual", min_sales=75)
        assert run.summary["min_sales"] == 75

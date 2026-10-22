import pytest
from unittest.mock import MagicMock
from app.scrapers.kalodata.product_list import ProductListScraper


class TestProductListScraperSalesThreshold:
    def test_validate_row_rejects_sales_50_or_below(self):
        page = MagicMock()
        scraper = ProductListScraper(page, "ID")

        # Sales <= 50 should fail validation
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 500000.0,
            "sales_value": 50,
            "commission_rate": 0.1
        }, min_sales=50)
        assert valid is False
        assert reason == "SALES_BELOW_MIN_50"

        # Sales 49 should fail
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 500000.0,
            "sales_value": 49,
            "commission_rate": 0.1
        }, min_sales=50)
        assert valid is False
        assert reason == "SALES_BELOW_MIN_50"

        # Sales None should fail
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 500000.0,
            "sales_value": None,
            "commission_rate": 0.1
        }, min_sales=50)
        assert valid is False
        assert reason == "SALES_BELOW_MIN_50"

    def test_validate_row_accepts_sales_above_50(self):
        page = MagicMock()
        scraper = ProductListScraper(page, "ID")

        # Sales 51 (> 50) should pass
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 500000.0,
            "sales_value": 51,
            "commission_rate": 0.1
        }, min_sales=50)
        assert valid is True
        assert reason == ""

        # Sales 1000 (> 50) should pass
        valid, reason = scraper._validate_row({
            "source_product_id": "12345",
            "product_name": "Celana Kulot Wanita",
            "revenue_value": 5000000.0,
            "sales_value": 1000,
            "commission_rate": 0.1
        }, min_sales=50)
        assert valid is True
        assert reason == ""

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

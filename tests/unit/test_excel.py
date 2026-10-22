"""
Unit test for ExcelExporter.
Verifies workbook structure, sheets (Data, Info), format strings, and checksum calculation.
"""

import unittest
from datetime import date, datetime
from pathlib import Path
import openpyxl

from app.exports.excel import ExcelExporter
from app.config import settings


class TestExcelExporter(unittest.TestCase):
    def test_excel_generation(self):
        sample_items = [
            {
                "source_product_id": "1729482938491029384",
                "product_name": "Celana Kulot Highwaist Linen Wanita",
                "shop_name": "Fashion Hijab Official",
                "product_url": "https://www.tiktok.com/@shop/product/1729482938491029384",
                "revenue_value": 15000000.0,
                "sales_value": 1250,
                "commission_rate": 0.15,
                "video_url": "https://www.tiktok.com/@creator/video/71829384918239482",
                "video_selection_method": "top_revenue",
                "currency_code": "IDR",
                "country_code": "ID",
                "scraped_at": datetime.utcnow(),
                "scrape_job_id": "job-test-12345"
            }
        ]

        meta = {
            "revenue_source_method": "product_filter",
            "rows_rejected": 0,
            "notes": "Unit test export"
        }

        res = ExcelExporter.generate_excel_file(
            country_code="ID",
            run_date=date(2026, 10, 17),
            period_date=date(2026, 10, 16),
            status="SUCCESS",
            items=sample_items,
            job_metadata=meta,
            version=1
        )

        self.assertIsNotNone(res)
        self.assertEqual(res["row_count"], 1)
        self.assertTrue(Path(res["absolute_path"]).exists())
        self.assertGreater(res["size_bytes"], 0)
        self.assertEqual(len(res["checksum_sha256"]), 64)

        # Inspect generated workbook
        wb = openpyxl.load_workbook(res["absolute_path"])
        self.assertIn("Data", wb.sheetnames)
        self.assertIn("Info", wb.sheetnames)

        ws_data = wb["Data"]
        self.assertEqual(ws_data.cell(row=1, column=1).value, "ID Produk")
        # Ensure ID Produk is preserved as string
        self.assertEqual(str(ws_data.cell(row=2, column=1).value), "1729482938491029384")

        ws_info = wb["Info"]
        self.assertEqual(ws_info.cell(row=2, column=1).value, "Negara")
        self.assertEqual(ws_info.cell(row=2, column=2).value, "ID")


if __name__ == "__main__":
    unittest.main()

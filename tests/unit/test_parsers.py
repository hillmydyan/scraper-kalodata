"""
Unit tests for NumberParser.
Supports both unittest (standard library) and pytest.
Meets acceptance criteria in PRD §16: >= 20 test cases per country, per suffix, and failure cases.
"""

import unittest
from app.scrapers.kalodata.parsers import NumberParser


class TestNumberParser(unittest.TestCase):
    def test_indonesia_revenue_parsing(self):
        # ID standard with Rp and various suffixes
        val, abbr = NumberParser.parse_currency_amount("Rp 1,2jt", "ID")
        self.assertEqual(val, 1200000.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("Rp 500rb", "ID")
        self.assertEqual(val, 500000.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("Rp 2.500.000", "ID")
        self.assertEqual(val, 2500000.0)
        self.assertFalse(abbr)

        val, abbr = NumberParser.parse_currency_amount("Rp150K", "ID")
        self.assertEqual(val, 150000.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("1,5M", "ID")
        self.assertEqual(val, 1500000.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("Rp 10 Miliar", "ID")
        self.assertEqual(val, 10000000000.0)
        self.assertTrue(abbr)

    def test_malaysia_revenue_parsing(self):
        # MY standard with RM, dot decimal, comma thousand
        val, abbr = NumberParser.parse_currency_amount("RM 12.5K", "MY")
        self.assertEqual(val, 12500.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("RM1.2M", "MY")
        self.assertEqual(val, 1200000.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("RM 250", "MY")
        self.assertEqual(val, 250.0)
        self.assertFalse(abbr)

        val, abbr = NumberParser.parse_currency_amount("RM 1,500.50", "MY")
        self.assertEqual(val, 1500.50)
        self.assertFalse(abbr)

        val, abbr = NumberParser.parse_currency_amount("RM 3.5B", "MY")
        self.assertEqual(val, 3500000000.0)
        self.assertTrue(abbr)

    def test_thailand_revenue_parsing(self):
        # TH standard with ฿, dot decimal, comma thousand
        val, abbr = NumberParser.parse_currency_amount("฿1.2M", "TH")
        self.assertEqual(val, 1200000.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("฿ 500K", "TH")
        self.assertEqual(val, 500000.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("฿15,000", "TH")
        self.assertEqual(val, 15000.0)
        self.assertFalse(abbr)

        val, abbr = NumberParser.parse_currency_amount("฿99.99", "TH")
        self.assertEqual(val, 99.99)
        self.assertFalse(abbr)

    def test_cross_currency_and_region_parsing(self):
        # Kalodata displays Rp/JT/RB when Indonesian UI is active across MY & TH
        val, abbr = NumberParser.parse_currency_amount("Rp39,65JT", "MY")
        self.assertEqual(val, 39650000.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("Rp103,80RB", "MY")
        self.assertEqual(val, 103800.0)
        self.assertTrue(abbr)

        val, abbr = NumberParser.parse_currency_amount("Rp127,98JT", "TH")
        self.assertEqual(val, 127980000.0)
        self.assertTrue(abbr)

        self.assertEqual(NumberParser.detect_currency("Rp39,65JT", "MY"), "IDR")
        self.assertEqual(NumberParser.detect_currency("RM 12.5K", "MY"), "MYR")
        self.assertEqual(NumberParser.detect_currency("฿1.2M", "TH"), "THB")

    def test_sales_volume_parsing(self):
        self.assertEqual(NumberParser.parse_integer_sales("1.2K", "ID"), 1200)
        self.assertEqual(NumberParser.parse_integer_sales("500", "ID"), 500)
        self.assertEqual(NumberParser.parse_integer_sales("15.5K", "MY"), 15500)
        self.assertEqual(NumberParser.parse_integer_sales("10,000", "TH"), 10000)

    def test_commission_rate_parsing(self):
        self.assertEqual(NumberParser.parse_commission_rate("15%"), 0.15)
        self.assertEqual(NumberParser.parse_commission_rate("10.5%"), 0.105)
        self.assertEqual(NumberParser.parse_commission_rate("0.20"), 0.20)
        self.assertEqual(NumberParser.parse_commission_rate("5,5%"), 0.055)
        self.assertEqual(NumberParser.parse_commission_rate("18"), 0.18)

    def test_failure_and_edge_cases(self):
        # Null and empty values must return None (§0.2: dilarang mengisi nilai tebakan)
        self.assertEqual(NumberParser.parse_currency_amount("", "ID"), (None, False))
        self.assertEqual(NumberParser.parse_currency_amount("-", "ID"), (None, False))
        self.assertEqual(NumberParser.parse_currency_amount("N/A", "ID"), (None, False))
        self.assertEqual(NumberParser.parse_currency_amount(None, "ID"), (None, False))
        self.assertEqual(NumberParser.parse_currency_amount("abc", "ID"), (None, False))

        self.assertIsNone(NumberParser.parse_integer_sales("", "ID"))
        self.assertIsNone(NumberParser.parse_integer_sales("-", "ID"))
        self.assertIsNone(NumberParser.parse_integer_sales(None, "ID"))

        self.assertIsNone(NumberParser.parse_commission_rate(""))
        self.assertIsNone(NumberParser.parse_commission_rate("-"))
        self.assertIsNone(NumberParser.parse_commission_rate("N/A"))
        self.assertIsNone(NumberParser.parse_commission_rate(None))
        self.assertIsNone(NumberParser.parse_commission_rate("150%"))


if __name__ == "__main__":
    unittest.main()

import pytest
from unittest.mock import MagicMock, patch
from app.scrapers.kalodata.creator_scraper import CreatorScraper


class TestCreatorScraperRevenueThreshold:
    def test_creator_revenue_filter_stops_when_below_threshold(self):
        page = MagicMock()
        context = MagicMock()
        page.context = context
        prod_tab = MagicMock()
        context.new_page.return_value = prod_tab

        # Mock 3 rows:
        # Row 1: Rp 10M (> 4jt)
        # Row 2: Rp 5JT (> 4jt)
        # Row 3: Rp 3,5JT (< 4jt) -> should cause loop to stop!
        # Row 4: Rp 2JT (< 4jt) -> should never be touched!
        def make_mock_row(rank_str, name_str, rev_str):
            row = MagicMock()
            td0 = MagicMock()
            td0.inner_text.return_value = rank_str
            td1 = MagicMock()
            td1.inner_text.return_value = name_str
            td1.locator.return_value.first = MagicMock(count=lambda: 0)
            td2 = MagicMock()
            td2.inner_text.return_value = rev_str
            row.locator.return_value.all.return_value = [td0, td1, td2]
            return row

        row1 = make_mock_row("1", "@creator1", "Rp 10M")
        row2 = make_mock_row("2", "@creator2", "Rp 5JT")
        row3 = make_mock_row("3", "@creator3", "Rp 3,5JT")
        row4 = make_mock_row("4", "@creator4", "Rp 2JT")

        page.locator.return_value.all.return_value = [row1, row2, row3, row4]

        # Mock detail page
        detail_tab = MagicMock()
        detail_tab.is_closed.return_value = False
        detail_tab.evaluate.return_value = [
            {"index": 1, "rowKey": "p1", "name": "Prod 1", "revenue": "Rp 1JT", "sales": "100"}
        ]
        context.expect_page.return_value.__enter__.return_value = MagicMock(value=detail_tab)

        scraper = CreatorScraper(page, "ID")
        # No max_creators limit: should stop automatically when it hits row 3 (< 4jt)
        res = scraper.scrape_creators(max_creators=None, min_revenue=4000000.0)

        # Only row 1 and row 2 should be scanned (total 2 creators)
        assert res["total_creators"] == 2
        assert len(res["items"]) == 2

    def test_creator_revenue_filter_manual_cap(self):
        page = MagicMock()
        context = MagicMock()
        page.context = context
        prod_tab = MagicMock()
        context.new_page.return_value = prod_tab

        # Mock 3 rows with high revenue
        def make_mock_row(rank_str, name_str, rev_str):
            row = MagicMock()
            td0 = MagicMock()
            td0.inner_text.return_value = rank_str
            td1 = MagicMock()
            td1.inner_text.return_value = name_str
            td1.locator.return_value.first = MagicMock(count=lambda: 0)
            td2 = MagicMock()
            td2.inner_text.return_value = rev_str
            row.locator.return_value.all.return_value = [td0, td1, td2]
            return row

        row1 = make_mock_row("1", "@creator1", "Rp 20M")
        row2 = make_mock_row("2", "@creator2", "Rp 18M")
        row3 = make_mock_row("3", "@creator3", "Rp 15M")

        page.locator.return_value.all.return_value = [row1, row2, row3]

        detail_tab = MagicMock()
        detail_tab.is_closed.return_value = False
        detail_tab.evaluate.return_value = [
            {"index": 1, "rowKey": "p1", "name": "Prod 1", "revenue": "Rp 1JT", "sales": "100"}
        ]
        context.expect_page.return_value.__enter__.return_value = MagicMock(value=detail_tab)

        scraper = CreatorScraper(page, "ID")
        # Manual cap of 1: even though all rows are > 4jt, manual cap limits to 1
        res = scraper.scrape_creators(max_creators=1, min_revenue=4000000.0)
        assert res["total_creators"] == 1
        assert len(res["items"]) == 1

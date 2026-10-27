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

        row1 = make_mock_row("1", "@creator1", "Rp 80M")
        row2 = make_mock_row("2", "@creator2", "Rp 70M")
        row3 = make_mock_row("3", "@creator3", "Rp 60M")

        page.locator.return_value.all.return_value = [row1, row2, row3]

        detail_tab = MagicMock()
        detail_tab.is_closed.return_value = False
        detail_tab.evaluate.return_value = [
            {"index": 1, "rowKey": "p1", "name": "Prod 1", "revenue": "Rp 1JT", "sales": "100"}
        ]
        context.expect_page.return_value.__enter__.return_value = MagicMock(value=detail_tab)

        scraper = CreatorScraper(page, "ID")
        # Manual cap of 1: even though all rows are > 50jt, manual cap limits to 1
        res = scraper.scrape_creators(max_creators=1, min_revenue=50000000.0)
        assert res["total_creators"] == 1
        assert len(res["items"]) == 1

    def test_creator_revenue_filter_50m_idr(self):
        page = MagicMock()
        context = MagicMock()
        page.context = context
        prod_tab = MagicMock()
        context.new_page.return_value = prod_tab

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

        # Row 1: Rp 120JT (> 50jt) -> included
        # Row 2: Rp 60JT (> 50jt)  -> included
        # Row 3: Rp 45JT (< 50jt)  -> stops!
        # Row 4: Rp 30JT (< 50jt)  -> skipped!
        row1 = make_mock_row("1", "@creator1", "Rp 120JT")
        row2 = make_mock_row("2", "@creator2", "Rp 60JT")
        row3 = make_mock_row("3", "@creator3", "Rp 45JT")
        row4 = make_mock_row("4", "@creator4", "Rp 30JT")
        page.locator.return_value.all.return_value = [row1, row2, row3, row4]

        detail_tab = MagicMock()
        detail_tab.is_closed.return_value = False
        detail_tab.evaluate.return_value = [
            {"index": 1, "rowKey": "p1", "name": "Prod 1", "revenue": "Rp 1JT", "sales": "100"}
        ]
        context.expect_page.return_value.__enter__.return_value = MagicMock(value=detail_tab)

        scraper = CreatorScraper(page, "ID")
        res = scraper.scrape_creators(max_creators=None, min_revenue=50000000.0)
        assert res["total_creators"] == 2
        assert len(res["items"]) == 2

    def test_creator_revenue_filter_myr_and_thb(self):
        page = MagicMock()
        context = MagicMock()
        page.context = context
        prod_tab = MagicMock()
        context.new_page.return_value = prod_tab

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

        # Test Malaysia (threshold 14000 MYR):
        # Row 1: RM 25K (> 14K)
        # Row 2: RM 15K (> 14K)
        # Row 3: RM 10K (< 14K) -> stops!
        row_my1 = make_mock_row("1", "@my_c1", "RM 25K")
        row_my2 = make_mock_row("2", "@my_c2", "RM 15K")
        row_my3 = make_mock_row("3", "@my_c3", "RM 10K")
        page.locator.return_value.all.return_value = [row_my1, row_my2, row_my3]

        detail_tab = MagicMock()
        detail_tab.is_closed.return_value = False
        detail_tab.evaluate.return_value = [
            {"index": 1, "rowKey": "p1", "name": "Prod 1", "revenue": "RM 500", "sales": "10"}
        ]
        context.expect_page.return_value.__enter__.return_value = MagicMock(value=detail_tab)

        scraper_my = CreatorScraper(page, "MY")
        res_my = scraper_my.scrape_creators(max_creators=None, min_revenue=14000.0)
        assert res_my["total_creators"] == 2

        # Test Thailand (threshold 110000 THB):
        # Row 1: ฿ 200K (> 110K)
        # Row 2: ฿ 120K (> 110K)
        # Row 3: ฿ 80K (< 110K) -> stops!
        row_th1 = make_mock_row("1", "@th_c1", "฿ 200K")
        row_th2 = make_mock_row("2", "@th_c2", "฿ 120K")
        row_th3 = make_mock_row("3", "@th_c3", "฿ 80K")
        page.locator.return_value.all.return_value = [row_th1, row_th2, row_th3]

        scraper_th = CreatorScraper(page, "TH")
        res_th = scraper_th.scrape_creators(max_creators=None, min_revenue=110000.0)
        assert res_th["total_creators"] == 2

    def test_creator_revenue_filter_stops_on_threshold_even_with_high_max_creators(self):
        page = MagicMock()
        context = MagicMock()
        page.context = context
        prod_tab = MagicMock()
        context.new_page.return_value = prod_tab

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

        # Row 1: Rp 120JT (> 50jt) -> included
        # Row 2: Rp 60JT (> 50jt)  -> included
        # Row 3: Rp 45JT (< 50jt)  -> MUST STOP even if max_creators=500!
        # Row 4: Rp 30JT (< 50jt)  -> never scraped!
        row1 = make_mock_row("1", "@creator1", "Rp 120JT")
        row2 = make_mock_row("2", "@creator2", "Rp 60JT")
        row3 = make_mock_row("3", "@creator3", "Rp 45JT")
        row4 = make_mock_row("4", "@creator4", "Rp 30JT")
        page.locator.return_value.all.return_value = [row1, row2, row3, row4]

        detail_tab = MagicMock()
        detail_tab.is_closed.return_value = False
        detail_tab.evaluate.return_value = [
            {"index": 1, "rowKey": "p1", "name": "Prod 1", "revenue": "Rp 1JT", "sales": "100"}
        ]
        context.expect_page.return_value.__enter__.return_value = MagicMock(value=detail_tab)

        scraper = CreatorScraper(page, "ID")
        # Manual cap set to 500: must stop at row 3 and only return 2 creators
        res = scraper.scrape_creators(max_creators=500, min_revenue=50000000.0)
        assert res["total_creators"] == 2
        assert len(res["items"]) == 2

    def test_apply_filters_selects_7_days_by_default(self):
        page = MagicMock()
        scraper = CreatorScraper(page, "ID")

        dt_mock = MagicMock()
        dt_mock.is_visible.return_value = True
        btn_7_days = MagicMock()
        btn_7_days.is_visible.return_value = True

        def mock_locator(selector):
            loc = MagicMock()
            if "Tanggal" in selector or "Date" in selector:
                loc.first = dt_mock
            elif "ant-popover" in selector or "ant-dropdown" in selector or "7" in selector:
                loc.first = btn_7_days
                sub_loc = MagicMock()
                sub_loc.first = btn_7_days
                loc.locator.return_value = sub_loc
            else:
                loc.first = MagicMock(is_visible=lambda timeout=0: False)
            return loc

        page.locator.side_effect = mock_locator
        scraper.apply_filters()

        dt_mock.click.assert_called_with(force=True)
        btn_7_days.click.assert_called_with(force=True)

    def test_apply_filters_selects_kemarin_when_specified(self):
        page = MagicMock()
        scraper = CreatorScraper(page, "ID")

        dt_mock = MagicMock()
        dt_mock.is_visible.return_value = True
        btn_kemarin = MagicMock()
        btn_kemarin.is_visible.return_value = True

        def mock_locator(selector):
            loc = MagicMock()
            if "Tanggal" in selector or "Date" in selector:
                loc.first = dt_mock
            elif "ant-popover" in selector or "ant-dropdown" in selector or "Yesterday" in selector or "Kemarin" in selector:
                loc.first = btn_kemarin
                sub_loc = MagicMock()
                sub_loc.first = btn_kemarin
                loc.locator.return_value = sub_loc
            else:
                loc.first = MagicMock(is_visible=lambda timeout=0: False)
            return loc

        page.locator.side_effect = mock_locator
        scraper.apply_filters(date_preset="kemarin")

        dt_mock.click.assert_called_with(force=True)
        btn_kemarin.click.assert_called_with(force=True)


import pytest
from unittest.mock import MagicMock
from app.scrapers.kalodata.navigation import KalodataNavigator, NavigationError


class TestKalodataNavigatorRegionSwitch:
    def test_switch_already_on_target_region(self):
        page = MagicMock()
        dropdown = MagicMock()
        dropdown.is_visible.return_value = True
        dropdown.inner_text.return_value = "MY \ue6e4"

        page.locator.return_value.first = dropdown

        nav = KalodataNavigator(page)
        res = nav.switch_and_verify_region("MY")
        assert res is True
        # Should not click dropdown if already on target
        dropdown.click.assert_not_called()

    def test_switch_to_new_region_success(self):
        page = MagicMock()
        page.url = "https://www.kalodata.com/creator"
        page.title.return_value = "Daftar Peringkat Kreator TikTok Shop Malaysia"

        # Initially dropdown shows ID
        dropdown = MagicMock()
        dropdown.is_visible.return_value = True
        dropdown.inner_text.side_effect = ["ID \ue6e4", "MY \ue6e4"]

        popover = MagicMock()
        popover.is_visible.return_value = True
        opt = MagicMock()
        opt.is_visible.return_value = True
        popover.locator.return_value.first = opt

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if selector == "#region-dropdown":
                mock_loc.first = dropdown
            elif "region-dropdown-popover" in selector:
                mock_loc.first = popover
            else:
                mock_loc.first = MagicMock(is_visible=lambda timeout=None: False)
            return mock_loc

        page.locator.side_effect = locator_side_effect

        nav = KalodataNavigator(page)
        res = nav.switch_and_verify_region("MY")
        assert res is True
        assert dropdown.click.called
        assert opt.click.called

    def test_switch_region_mismatch_raises(self):
        page = MagicMock()
        page.url = "https://www.kalodata.com/creator"
        page.title.return_value = "Daftar Peringkat Kreator TikTok Shop Indonesia"

        dropdown = MagicMock()
        dropdown.is_visible.return_value = True
        dropdown.inner_text.return_value = "ID \ue6e4"

        page.locator.return_value.first = dropdown

        nav = KalodataNavigator(page)
        with pytest.raises(NavigationError) as exc_info:
            nav.switch_and_verify_region("MY")
        assert exc_info.value.error_code == "COUNTRY_MISMATCH"


class TestKalodataNavigatorSalesFilter:
    def test_apply_sales_filter_no_thresholds_returns_false(self):
        page = MagicMock()
        nav = KalodataNavigator(page)
        assert nav.apply_sales_filter(None, None) is False
        assert nav.apply_sales_filter(0, 0) is False

    def test_apply_sales_filter_success(self):
        page = MagicMock()

        # Trigger candidate
        cand = MagicMock()
        cand.is_visible.return_value = True
        cand.bounding_box.return_value = {"x": 120, "y": 250, "width": 80, "height": 30}
        cand.evaluate.return_value = False  # not in table
        page.get_by_text.return_value.all.return_value = [cand]

        # Popover and inputs
        popover = MagicMock()
        popover.is_visible.return_value = True
        min_input = MagicMock()
        max_input = MagicMock()

        input_loc = MagicMock()
        input_loc.all.return_value = [min_input, max_input]

        ok_btn = MagicMock()
        ok_btn.is_visible.return_value = True

        submit_btn = MagicMock()
        submit_btn.is_visible.return_value = True
        submit_btn.is_enabled.return_value = True

        def page_loc_side_effect(selector):
            mock_loc = MagicMock()
            if "ant-popover" in selector:
                mock_loc.last = popover
            elif "button:has-text('Submit')" in selector or "button:has-text('Kirim')" in selector:
                mock_loc.first = submit_btn
            else:
                mock_loc.first = MagicMock(is_visible=lambda timeout=None: False)
                mock_loc.last = MagicMock(is_visible=lambda timeout=None: False)
            return mock_loc

        button_loc = MagicMock()
        button_loc.filter.return_value.last = ok_btn

        def popover_loc_side_effect(selector):
            if selector == "input":
                return input_loc
            if selector == "button":
                return button_loc
            mock_loc = MagicMock()
            if "OK" in selector:
                mock_loc.last = ok_btn
            return mock_loc

        page.locator.side_effect = page_loc_side_effect
        popover.locator.side_effect = popover_loc_side_effect

        nav = KalodataNavigator(page)
        res = nav.apply_sales_filter(min_sales=1000, max_sales=10000)

        assert res is True
        cand.click.assert_called_once()
        min_input.fill.assert_any_call("1000")
        max_input.fill.assert_any_call("10000")
        ok_btn.click.assert_called_once()
        submit_btn.click.assert_called_once()


class TestKalodataNavigatorRevenueFilter:
    def test_apply_revenue_source_filter_already_active(self):
        page = MagicMock()
        video_badge = MagicMock()
        video_badge.is_visible.return_value = True
        video_badge.bounding_box.return_value = {"x": 100, "y": 200, "width": 50, "height": 20}

        mock_loc = MagicMock()
        mock_loc.filter.return_value.all.return_value = [video_badge]
        page.locator.return_value = mock_loc

        nav = KalodataNavigator(page)
        res = nav.apply_revenue_source_filter()
        assert res == "product_filter"

    def test_apply_revenue_source_filter_clicks_video_and_ok(self):
        page = MagicMock()

        # Trigger
        cand = MagicMock()
        cand.is_visible.return_value = True
        cand.bounding_box.return_value = {"x": 100, "y": 250, "width": 80, "height": 30}
        cand.inner_text.return_value = "Sumber Pendapatan(Konten)"
        cand.evaluate.return_value = False
        page.get_by_text.return_value.all.return_value = [cand]

        popover = MagicMock()
        popover.is_visible.return_value = True
        video_opt = MagicMock()
        video_opt.is_visible.return_value = True
        ok_btn = MagicMock()
        ok_btn.is_visible.return_value = True
        submit_btn = MagicMock()
        submit_btn.is_visible.return_value = True
        submit_btn.is_enabled.return_value = True

        def page_loc_side_effect(selector):
            mock = MagicMock()
            if "ant-popover" in selector:
                mock.last = popover
            elif "button:has-text('Submit')" in selector or "button:has-text('Kirim')" in selector:
                mock.first = submit_btn
            else:
                mock.filter.return_value.all.return_value = []
                mock.first = MagicMock(is_visible=lambda timeout=None: False)
                mock.last = MagicMock(is_visible=lambda timeout=None: False)
            return mock

        def popover_loc_side_effect(selector):
            mock = MagicMock()
            if "Video" in selector:
                mock.first = video_opt
            elif "OK" in selector:
                mock.last = ok_btn
            else:
                mock.first = MagicMock(is_visible=lambda timeout=None: False)
                mock.last = MagicMock(is_visible=lambda timeout=None: False)
            return mock

        page.locator.side_effect = page_loc_side_effect
        popover.locator.side_effect = popover_loc_side_effect
        popover.get_by_text.return_value.first = video_opt
        popover.get_by_role.return_value.last = ok_btn

        nav = KalodataNavigator(page)
        res = nav.apply_revenue_source_filter()
        assert res == "product_filter"
        cand.click.assert_called_once()
        video_opt.click.assert_called_once()




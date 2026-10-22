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

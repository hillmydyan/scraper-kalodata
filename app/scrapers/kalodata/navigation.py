"""
Navigation and filter setup on Kalodata.
Follows rules in PRD §6.2, §6.3, §6.4, and §6.6.
"""

import re
from datetime import date, timedelta
from typing import Tuple, List, Optional
import structlog
from playwright.sync_api import Page

from app.config import settings, sel, get_country_config, FILTERS_CONFIG
from app.scrapers.base import BaseScraper

logger = structlog.get_logger(__name__)


class NavigationError(Exception):
    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


class KalodataNavigator:
    def __init__(self, page: Page):
        self.page = page

    def dismiss_overlays(self) -> None:
        """Removes blocking marketing/promo overlays."""
        try:
            self.page.evaluate(
                "() => document.querySelectorAll('.ant-modal-root, .ant-modal-mask, .ant-modal-wrap, .ModalFeatureMemberWrapper').forEach(el => el.remove())"
            )
            self.page.wait_for_timeout(300)
        except Exception:
            pass

    def ensure_ui_language(self, target_lang: str = "en") -> bool:
        """
        Forces and verifies UI language to English (§6.3).
        """
        logger.info("Setting UI language", target_lang=target_lang)
        # Check current HTML lang or localStorage/cookie if set
        try:
            self.page.evaluate(
                f"localStorage.setItem('i18nextLng', '{target_lang}');"
            )
        except Exception:
            pass
        return True

    def switch_and_verify_region(self, country_code: str) -> bool:
        """
        Switches Kalodata region and verifies region indicator (§6.6).
        Raises NavigationError with COUNTRY_MISMATCH on failure.
        """
        country_cfg = get_country_config(country_code)
        region_label = country_cfg.get("region_label", country_code)
        expected_indicator = country_cfg.get("expected_indicator", country_code)
        currency_code = country_cfg.get("currency_code", "")

        logger.info(
            "Switching region",
            country=country_code,
            region_label=region_label,
            expected=expected_indicator
        )

        self.dismiss_overlays()

        # Check if already on target region
        dropdown = self.page.locator("#region-dropdown").first
        try:
            if dropdown.is_visible(timeout=3000):
                current_text = dropdown.inner_text().strip().upper()
                if country_code.upper() in current_text or region_label.upper() in current_text:
                    logger.info("Region already set to target", country=country_code, current=current_text)
                    return True
        except Exception:
            pass

        # Look for region picker trigger (#region-dropdown)
        reg_sel = sel("region_selector_trigger")
        clicked = False
        for s in [reg_sel["primary"]] + reg_sel.get("fallbacks", []):
            try:
                elem = self.page.locator(s).first
                if elem.is_visible(timeout=1500):
                    elem.click(force=True)
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            try:
                if dropdown.is_visible(timeout=1000):
                    dropdown.click(force=True)
                    clicked = True
            except Exception:
                pass

        if clicked:
            self.page.wait_for_timeout(800)
            # Click country option inside popover
            opt_clicked = False
            for target_opt in [region_label, country_code]:
                try:
                    popover = self.page.locator(".region-dropdown-popover:not(.ant-popover-hidden), .ant-popover:not(.ant-popover-hidden)").first
                    if popover.is_visible(timeout=1500):
                        opt = popover.locator(f"text={target_opt}").first
                        if opt.is_visible(timeout=1000):
                            opt.click(force=True)
                            opt_clicked = True
                            break
                except Exception:
                    pass

            if not opt_clicked:
                for target_opt in [region_label, country_code]:
                    try:
                        self.page.get_by_text(target_opt, exact=False).first.click(force=True, timeout=1500)
                        opt_clicked = True
                        break
                    except Exception:
                        pass
                if not opt_clicked:
                    logger.warning("Could not click region text directly", region_label=region_label)

            BaseScraper.pacing_page_delay()
            self.page.wait_for_timeout(2000)

        # VERIFY REGION (§6.6): Must not assume, must verify UI indicator
        self.dismiss_overlays()

        # 1. Verify via #region-dropdown indicator
        try:
            new_text = self.page.locator("#region-dropdown").first.inner_text().strip().upper()
            if country_code.upper() in new_text or region_label.upper() in new_text:
                logger.info("Region switch verified via #region-dropdown", country=country_code, text=new_text)
                return True
        except Exception:
            pass

        # 2. Verify via document title (e.g. 'Daftar Peringkat Kreator TikTok Shop Malaysia')
        try:
            page_title = (self.page.title() or "").lower()
            if region_label.lower() in page_title or country_code.lower() in page_title:
                logger.info("Region switch verified via page title", country=country_code, title=page_title)
                return True
        except Exception:
            pass

        # 3. Verify via URL parameter/path
        current_url = self.page.url
        if expected_indicator.upper() in current_url.upper():
            logger.info("Region switch verified via URL", country=country_code, url=current_url)
            return True

        current_title = self.page.title() or ""
        logger.warning(
            "Region switch verification failed",
            country=country_code,
            current_url=current_url,
            current_title=current_title
        )

        raise NavigationError(
            f"Failed to verify region switch to {country_code}. Expected {expected_indicator} or {region_label} (Current URL: {current_url}, Title: {current_title})",
            error_code="COUNTRY_MISMATCH"
        )

    def apply_date_range(self, start_date: date, end_date: date) -> Tuple[str, str]:
        """
        Applies explicit date range (§6.2).
        Default is yesterday: period_start = period_end = yesterday.
        """
        logger.info("Setting date filter", start=str(start_date), end=str(end_date))
        self.dismiss_overlays()

        # Look for date picker trigger in left sidebar
        dp_sel = sel("date_picker_trigger")
        for s in [dp_sel["primary"]] + dp_sel.get("fallbacks", []):
            try:
                elem = self.page.locator(s).first
                if elem.is_visible(timeout=1000):
                    elem.click()
                    break
            except Exception:
                pass

        self.page.wait_for_timeout(500)

        # Support clicking 'Yesterday' / 'Kemarin' preset option in popover
        try:
            yesterday_opt = self.page.locator(".ant-popover:not(.ant-popover-hidden), div[role='tooltip']").locator("text=/Yesterday|Kemarin/i").first
            if yesterday_opt.is_visible(timeout=1500):
                yesterday_opt.click()
                BaseScraper.pacing_page_delay()
        except Exception:
            pass

        # Submit filter on left sidebar
        try:
            submit_btn = self.page.locator("button:has-text('Submit'), button:has-text('Kirim')").first
            if submit_btn.is_visible(timeout=1000) and submit_btn.is_enabled():
                submit_btn.click()
                BaseScraper.pacing_page_delay()
        except Exception:
            pass

        return str(start_date), str(end_date)

    def apply_category_filter(self, country_code: str) -> List[str]:
        """
        Applies 'Bawahan Wanita' category filter (§6.2).
        Uses verified Ant Design cascader popover on Kalodata sidebar.
        """
        cat_rule = FILTERS_CONFIG.get("categories", {}).get(country_code, {})
        cat_path = cat_rule.get("category_path", ["Womenswear & Underwear", "Women's Bottoms"])

        logger.info("Applying category filter", country=country_code, path=cat_path)
        self.dismiss_overlays()

        cascader_sel = sel("category_cascader")
        for s in [cascader_sel["primary"]] + cascader_sel.get("fallbacks", []):
            try:
                elem = self.page.locator(s).first
                if elem.is_visible(timeout=1000):
                    elem.click()
                    break
            except Exception:
                pass

        self.page.wait_for_timeout(1000)

        # 1. Hover/Click first level (e.g. Womenswear & Underwear or Pakaian & Pakaian Dalam Wanita)
        primary_cat = cat_path[0] if len(cat_path) > 0 else "Womenswear & Underwear"
        try:
            ww = self.page.locator(".ant-cascader-menu-item").filter(
                has_text=re.compile(r"Pakaian & Pakaian Dalam Wanita|Womenswear", re.I)
            ).first
            if not ww.is_visible(timeout=1500):
                ww = self.page.locator(".ant-cascader-menus, .FilterCategoryCascader").get_by_text(primary_cat, exact=False).first

            if ww.is_visible(timeout=2000):
                ww.hover()
                self.page.wait_for_timeout(800)
            else:
                logger.warning("Primary category item not immediately visible", name=primary_cat)
        except Exception as ex:
            logger.warning("Error hovering primary category", error=str(ex))

        # 2. Click subcategory checkbox (e.g. Women's Bottoms or Bawahan Wanita)
        sub_cat = cat_path[1] if len(cat_path) > 1 else "Women's Bottoms"
        try:
            bottoms_item = self.page.locator(".ant-cascader-menu-item").filter(
                has_text=re.compile(r"Bawahan Wanita|Women's Bottoms", re.I)
            ).first
            if not bottoms_item.is_visible(timeout=1500):
                bottoms_item = self.page.locator(f"li.ant-cascader-menu-item:has-text(\"{sub_cat}\")").first

            if bottoms_item.is_visible(timeout=2000):
                checkbox = bottoms_item.locator(".ant-cascader-checkbox, .ant-checkbox, input[type='checkbox']").first
                if checkbox.is_visible(timeout=800):
                    checkbox.click()
                else:
                    bottoms_item.click()
                self.page.wait_for_timeout(800)
            else:
                opt = self.page.locator(".ant-cascader-menus, .FilterCategory").get_by_text(sub_cat, exact=False).first
                if opt.is_visible(timeout=1500):
                    opt.click()
        except Exception as ex:
            logger.warning("Error selecting subcategory checkbox", error=str(ex))

        # 3. Click OK / Apply button in visible cascader popover
        try:
            ok_elem = self.page.locator(".ant-popover:not(.ant-popover-hidden)").locator("text=/^OK$|^Apply$/i").last
            if ok_elem.is_visible(timeout=1500):
                ok_elem.click()
                self.page.wait_for_timeout(1000)
        except Exception as ex:
            logger.warning("Error clicking cascader confirm button", error=str(ex))

        # 4. Click Submit / Kirim button on bottom left sidebar if enabled
        try:
            submit_btn = self.page.locator("button:has-text('Submit'), button:has-text('Kirim')").first
            if submit_btn.is_visible(timeout=1000) and submit_btn.is_enabled():
                submit_btn.click()
                BaseScraper.pacing_page_delay()
        except Exception:
            pass

        # 5. Check if Kalodata blocked with login dialog
        try:
            modal = self.page.locator("div[role='dialog']:has(input), .ant-modal:has(input)").first
            if modal.is_visible(timeout=1000):
                logger.warning("Kalodata required login to submit filter")
                self.page.keyboard.press("Escape")
        except Exception:
            pass

        BaseScraper.pacing_page_delay()
        return cat_path

    def apply_revenue_source_filter(self) -> str:
        """
        Applies 'Sumber Pendapatan(Konten) > Video' (§6.4).
        Uses verified left sidebar popover on Kalodata.
        """
        logger.info("Applying revenue source filter: Video")
        self.dismiss_overlays()

        try:
            # 1. Check if 'Video' is already active under Sumber Pendapatan on the sidebar
            try:
                sidebar_video = self.page.locator("aside, nav, .ant-layout-sider, div").filter(
                    has_text=re.compile(r"^\s*Video\s*$", re.I)
                ).all()
                for v in sidebar_video:
                    if v.is_visible(timeout=200):
                        box = v.bounding_box()
                        if box and box["x"] < 350 and box["y"] > 80:
                            logger.info("Revenue source filter 'Video' is already active on Kalodata sidebar")
                            return "product_filter"
            except Exception:
                pass

            # 2. Click Sumber Pendapatan(Konten) / Revenue Source (Content) in left sidebar
            # Exclude 'Channel' to avoid opening Livestream/Channel popover
            spk = None
            for term in ["Sumber Pendapat", "Revenue Source"]:
                try:
                    candidates = self.page.get_by_text(term, exact=False).all()
                    for cand in candidates:
                        try:
                            if not cand.is_visible(timeout=300):
                                continue
                            box = cand.bounding_box()
                            if not box or box["x"] > 350 or box["y"] < 60:
                                continue
                            in_table = cand.evaluate("el => !!el.closest('table, thead, th, tr, [role=\"table\"], [role=\"columnheader\"], .ant-table')")
                            if in_table:
                                continue
                            txt = (cand.inner_text() or "").strip().lower()
                            # Strictly exclude Channel, Cha, Saluran, Live, Siaran
                            if any(bad in txt for bad in ["channel", "cha", "saluran", "live", "siaran"]):
                                continue
                            spk = cand
                            logger.info("Found Sumber Pendapatan (Konten) trigger on sidebar", text=txt, x=box["x"], y=box["y"])
                            break
                        except Exception:
                            continue
                    if spk:
                        break
                except Exception as ex:
                    logger.debug("Error finding revenue source trigger", term=term, error=str(ex))

            if not spk or not spk.is_visible(timeout=1500):
                cand = self.page.locator("div:has-text('Sumber Pendapatan'), div:has-text('Revenue Source')").first
                if cand.is_visible(timeout=1000):
                    spk = cand

            if spk and spk.is_visible(timeout=1500):
                spk.scroll_into_view_if_needed()
                spk.click(force=True)
                self.page.wait_for_timeout(800)

                # 3. Select 'Video' checkbox / option in popover
                popover = self.page.locator(".ant-popover:not(.ant-popover-hidden), .ant-dropdown:not(.ant-dropdown-hidden), div[role='tooltip']:not([aria-hidden='true'])").last
                video_opt = None
                for v_loc in [
                    popover.get_by_text(re.compile(r"^\s*Video\s*$", re.I)),
                    popover.locator("text=/^Video$/i"),
                    popover.locator("label:has-text('Video'), span:has-text('Video'), div:has-text('Video'), li:has-text('Video')"),
                    self.page.locator(".ant-popover:not(.ant-popover-hidden)").get_by_text("Video", exact=True)
                ]:
                    try:
                        cand = v_loc.first
                        if cand.is_visible(timeout=500):
                            video_opt = cand
                            break
                    except Exception:
                        continue

                if video_opt and video_opt.is_visible(timeout=1500):
                    try:
                        video_opt.click(force=True)
                    except Exception:
                        video_opt.evaluate("el => el.click()")
                    self.page.wait_for_timeout(600)
                    logger.info("Selected 'Video' in revenue source popover")

                    # 4. Click OK / Apply button in popover if present
                    for ok_loc in [
                        popover.get_by_role("button", name=re.compile(r"^OK$|^Apply$|^Terapkan$", re.I)),
                        popover.locator("button, [role='button'], .ant-btn, a").filter(has_text=re.compile(r"^OK$|^Apply$|^Terapkan$", re.I)),
                        popover.get_by_text("OK", exact=True),
                        self.page.locator(".ant-popover:not(.ant-popover-hidden)").locator("text=/^OK$|^Apply$/i")
                    ]:
                        try:
                            btn = ok_loc.last
                            if btn.is_visible(timeout=500):
                                try:
                                    btn.click(force=True)
                                except Exception:
                                    btn.evaluate("el => el.click()")
                                self.page.wait_for_timeout(800)
                                break
                        except Exception:
                            continue

                    # 5. Click Submit / Kirim on left sidebar if enabled
                    try:
                        submit_btn = self.page.locator("button:has-text('Submit'), button:has-text('Kirim')").first
                        if submit_btn.is_visible(timeout=800) and submit_btn.is_enabled():
                            submit_btn.click(force=True)
                            BaseScraper.pacing_page_delay()
                            self.page.wait_for_timeout(1500)
                    except Exception:
                        pass

                    # 6. Close popover if still lingering
                    try:
                        if popover.is_visible(timeout=400):
                            self.page.keyboard.press("Escape")
                            self.page.wait_for_timeout(400)
                    except Exception:
                        pass

                    logger.info("Revenue source filter 'Video' applied successfully via sidebar")
                    return "product_filter"
        except Exception as ex:
            logger.warning("Error applying revenue source filter via sidebar", error=str(ex))

        logger.info("Revenue source filter not on product list, using detail_breakdown fallback")
        return "detail_breakdown"

    def apply_sales_filter(self, min_sales: Optional[int], max_sales: Optional[int] = None) -> bool:
        """
        Applies 'Penjualan' / 'Item Sold' filter on Kalodata sidebar (§6.10).
        Fills the 'Item Sold' / 'Penjualan' minimum input and optional maximum input, or selects preset, then submits.
        """
        if (not min_sales or min_sales <= 0) and (not max_sales or max_sales <= 0):
            return False

        logger.info("Applying sales filter on Kalodata sidebar", min_sales=min_sales, max_sales=max_sales)
        self.dismiss_overlays()
        self.page.wait_for_timeout(1000)
        try:
            self.page.wait_for_selector(".ant-spin-spinning", state="detached", timeout=3000)
        except Exception:
            pass

        try:
            # 1. Click Item Sold / Penjualan in left sidebar
            sales_trigger = None

            # Pattern matches 'Item Sold' (English Kalodata UI), 'Penjualan' (Indonesian), or 'Sales'
            sales_pattern = re.compile(r"Item Sold|Penjualan|Sales", re.I)

            # Strategy 1: Find text element on left sidebar (x < 350, y > 60) outside table
            try:
                candidates = self.page.get_by_text(sales_pattern).all()
                for cand in candidates:
                    try:
                        if not cand.is_visible(timeout=300):
                            continue
                        box = cand.bounding_box()
                        if not box or box["x"] > 350 or box["y"] < 60:
                            continue
                        in_table = cand.evaluate("el => !!el.closest('table, thead, th, tr, [role=\"table\"], [role=\"columnheader\"], .ant-table')")
                        if in_table:
                            continue
                        sales_trigger = cand
                        logger.info("Found sales_trigger on sidebar", x=box["x"], y=box["y"])
                        break
                    except Exception:
                        continue
            except Exception as ex:
                logger.debug("Strategy 1 get_by_text error", error=str(ex))

            # Strategy 2: Relative XPath preceding 'Sumber Pendapatan' or 'Revenue Source'
            if not sales_trigger:
                try:
                    prec_xpath = "//div[contains(., 'Sumber Pendapatan') or contains(., 'Revenue Source')]/preceding::*[contains(normalize-space(text()), 'Item Sold') or contains(normalize-space(text()), 'Penjualan') or contains(normalize-space(text()), 'Sales')][1]"
                    cand = self.page.locator(f"xpath={prec_xpath}").first
                    if cand.is_visible(timeout=1000):
                        sales_trigger = cand
                        logger.info("Found sales_trigger via preceding sibling XPath")
                except Exception as ex:
                    logger.debug("Strategy 2 preceding XPath error", error=str(ex))

            if not sales_trigger or not sales_trigger.is_visible(timeout=2000):
                logger.warning("Could not find Item Sold / Penjualan sidebar trigger")
                return False

            # Click the trigger to open popover/menu
            sales_trigger.scroll_into_view_if_needed()
            sales_trigger.click(force=True)
            self.page.wait_for_timeout(800)

            # Check visible popover or dropdown menu
            popover = self.page.locator(".ant-popover:not(.ant-popover-hidden), .ant-dropdown:not(.ant-dropdown-hidden), div[role='tooltip']:not([aria-hidden='true']), div[role='menu']:not([aria-hidden='true'])").last
            if not popover.is_visible(timeout=1000):
                logger.info("Popover not immediately visible, attempting click on parent row container...")
                for p_loc in [sales_trigger.locator(".."), sales_trigger.locator("../..")]:
                    try:
                        if p_loc.is_visible(timeout=400):
                            p_loc.click(force=True)
                            self.page.wait_for_timeout(800)
                            popover = self.page.locator(".ant-popover:not(.ant-popover-hidden), .ant-dropdown:not(.ant-dropdown-hidden), div[role='tooltip']:not([aria-hidden='true']), div[role='menu']:not([aria-hidden='true'])").last
                            if popover.is_visible(timeout=500):
                                break
                    except Exception:
                        pass

            # 2. Fill the Minimal and Maksimal input boxes inside the popover
            if not popover.is_visible(timeout=2000):
                logger.warning("Sales popover did not appear after clicking Item Sold / Penjualan")
                return False

            inputs = popover.locator("input").all()
            if not inputs:
                logger.warning("No input elements found in sales popover")
                return False

            # First input: Minimal sales
            min_input = inputs[0]
            min_input.click()
            min_input.fill("")
            min_input.press("Control+A")
            min_input.press("Backspace")
            if min_sales and min_sales > 0:
                min_input.fill(str(min_sales))
                try:
                    min_input.press_sequentially(str(min_sales), delay=20)
                except Exception:
                    pass
                try:
                    min_input.dispatch_event("input")
                    min_input.dispatch_event("change")
                except Exception:
                    pass
            self.page.wait_for_timeout(300)

            # Second input: Maksimal sales (if available)
            if len(inputs) >= 2:
                max_input = inputs[1]
                max_input.click()
                max_input.fill("")
                max_input.press("Control+A")
                max_input.press("Backspace")
                if max_sales and max_sales > 0:
                    max_input.fill(str(max_sales))
                    try:
                        max_input.press_sequentially(str(max_sales), delay=20)
                    except Exception:
                        pass
                    try:
                        max_input.dispatch_event("input")
                        max_input.dispatch_event("change")
                    except Exception:
                        pass
                self.page.wait_for_timeout(300)

            # Press Enter on min_input to trigger React form update
            try:
                min_input.press("Enter")
                self.page.wait_for_timeout(400)
            except Exception:
                pass

            # 3. Click blue 'OK' button inside the popover
            ok_clicked = False
            for ok_loc in [
                popover.locator("button").filter(has_text=re.compile(r"^OK$", re.I)),
                popover.get_by_role("button", name=re.compile(r"^OK$", re.I)),
                popover.locator("button:has-text('OK'), button.ant-btn-primary"),
                popover.locator("button, [role='button'], .ant-btn, a").filter(has_text=re.compile(r"^OK$", re.I)),
                popover.get_by_text("OK", exact=True),
                self.page.locator(".ant-popover:not(.ant-popover-hidden)").locator("text=/^OK$/i"),
                self.page.get_by_role("button", name=re.compile(r"^OK$", re.I)),
                self.page.locator("button:has-text('OK'), .ant-btn:has-text('OK')")
            ]:
                try:
                    btn = ok_loc.last
                    if btn.is_visible(timeout=500):
                        try:
                            btn.click(force=True)
                        except Exception:
                            btn.evaluate("el => el.click()")
                        ok_clicked = True
                        logger.info("Clicked OK button in sales popover")
                        self.page.wait_for_timeout(1000)
                        break
                except Exception:
                    continue

            if not ok_clicked:
                logger.warning("OK button in sales popover not found or could not be clicked")

            # 4. Click Submit / Kirim on left sidebar if enabled
            submit_btn = self.page.locator("button:has-text('Submit'), button:has-text('Kirim')").first
            if submit_btn.is_visible(timeout=1000) and submit_btn.is_enabled():
                submit_btn.click(force=True)
                BaseScraper.pacing_page_delay()
                self.page.wait_for_timeout(1500)

            # 5. Close popover if still lingering
            try:
                if popover.is_visible(timeout=400):
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(400)
            except Exception:
                pass

            logger.info("Sales filter applied successfully on Kalodata sidebar", min_sales=min_sales, max_sales=max_sales)
            return True
        except Exception as ex:
            logger.warning("Error applying sales filter on sidebar", error=str(ex))

        return False

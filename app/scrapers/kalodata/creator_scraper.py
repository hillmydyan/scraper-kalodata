"""
Creator Scraper for Kalodata.
Scrapes creators and their top 3 best-selling products from https://www.kalodata.com/creator.
Filters:
- Tanggal: 7 hari terakhir
- Kategori: Bawahan Wanita
- Sumber Pendapatan: Video
- Tipe Akun: Mandiri
"""

import re
import sys
import time
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Callable, Tuple
import structlog
from playwright.sync_api import Page

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.config import settings
from app.scrapers.base import BaseScraper
from app.scrapers.kalodata.parsers import NumberParser

logger = structlog.get_logger(__name__)


class CreatorScraper:
    def __init__(self, page: Page, country_code: str = "ID", job_id: Optional[str] = None):
        self.page = page
        self.country_code = country_code.upper()
        self.job_id = job_id
        self.currency_code = "IDR" if self.country_code == "ID" else ("MYR" if self.country_code == "MY" else "THB")

    def dismiss_overlays(self, target_page: Optional[Page] = None) -> None:
        """Removes blocking marketing/promo overlays."""
        p = target_page or self.page
        try:
            p.evaluate(
                "() => document.querySelectorAll('.ant-modal-root, .ant-modal-mask, .ant-modal-wrap, .ModalFeatureMemberWrapper').forEach(el => el.remove())"
            )
            p.wait_for_timeout(300)
        except Exception:
            pass

    def apply_filters(self, date_preset: str = "7_days") -> bool:
        """
        Applies:
        1. Tanggal: 7 hari terakhir (or Kemarin if date_preset == 'kemarin')
        2. Kategori: Bawahan Wanita
        3. Sumber Pendapatan: Video
        4. Tipe Akun: Mandiri
        5. Submit / Kirim
        """
        logger.info("Applying creator filters", country=self.country_code, date_preset=date_preset)
        self.dismiss_overlays()

        # 1. Date filter (default: 7 hari terakhir / Last 7 days)
        try:
            logger.info("Setting Creator Date Filter", date_preset=date_preset)
            dt = self.page.locator("div.cursor-pointer:has-text('Tanggal'), div.cursor-pointer:has-text('Date'), .ant-dropdown-trigger:has-text('Tanggal'), .ant-dropdown-trigger:has-text('Date')").first
            if dt.is_visible(timeout=2000):
                dt.click(force=True)
            else:
                self.page.locator("text=/^Tanggal$|^Date$/i").first.click(force=True)
            self.page.wait_for_timeout(800)

            if date_preset in ("kemarin", "yesterday"):
                btn_date = self.page.locator(".ant-popover:not(.ant-popover-hidden), .ant-dropdown:not(.ant-dropdown-hidden), div[role='tooltip']").locator("text=/Yesterday|^Kemarin$|Kemarin/i").first
                if not btn_date.is_visible(timeout=1500):
                    btn_date = self.page.locator("text=/Yesterday|^Kemarin$|Kemarin/i").first
            else:
                # Default: 7 hari terakhir / Last 7 days
                btn_date = self.page.locator(".ant-popover:not(.ant-popover-hidden), .ant-dropdown:not(.ant-dropdown-hidden), div[role='tooltip']").locator("text=/7\\s*hari\\s*terakhir|Last\\s*7\\s*days|Past\\s*7\\s*days/i").first
                if not btn_date.is_visible(timeout=1500):
                    btn_date = self.page.locator("text=/7\\s*hari\\s*terakhir|Last\\s*7\\s*days|Past\\s*7\\s*days/i").first

            if btn_date.is_visible(timeout=2000):
                btn_date.click(force=True)
            self.page.wait_for_timeout(800)
        except Exception as ex:
            logger.warning("Error applying date filter for creator", error=str(ex))

        # 2. Category: Bawahan Wanita
        try:
            logger.info("Setting Category: Bawahan Wanita")
            self.dismiss_overlays()
            self.page.evaluate("""() => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                while (node = walker.nextNode()) {
                    if (node.nodeValue && node.nodeValue.trim() === 'Kategori') {
                        const box = node.parentElement.getBoundingClientRect();
                        if (box.x < 200 && box.y > 100) {
                            node.parentElement.click();
                            break;
                        }
                    }
                }
            }""")
            self.page.wait_for_timeout(1000)

            pw = self.page.locator(".ant-cascader-menu-item:has-text('Pakaian & Pakaian Dalam Wanita'), .ant-cascader-menu-item:has-text('Womenswear')").first
            if pw.is_visible(timeout=2000):
                pw.hover()
                self.page.wait_for_timeout(800)
                bottoms = self.page.locator(".ant-cascader-menu-item:has-text('Bawahan Wanita'), .ant-cascader-menu-item:has-text(\"Women's Bottoms\")").first
                if bottoms.is_visible(timeout=2000):
                    bottoms.locator(".ant-cascader-checkbox, .ant-checkbox").first.click(force=True)
                    self.page.wait_for_timeout(500)
                    ok_btn = self.page.locator(".ant-popover:not(.ant-popover-hidden)").locator("text=/^OK$|^Apply$/i").last
                    if ok_btn.is_visible(timeout=1000):
                        ok_btn.click(force=True)
            self.page.wait_for_timeout(800)
        except Exception as ex:
            logger.warning("Error applying category filter for creator", error=str(ex))

        # 3. Sumber Pendapatan: Video
        try:
            logger.info("Setting Revenue Source: Video")
            self.dismiss_overlays()
            sp = self.page.locator(".ant-dropdown-trigger:has-text('Sumber Pendapatan')").first
            sp.scroll_into_view_if_needed()
            sp.click(force=True)
            self.page.wait_for_timeout(800)
            video_opt = self.page.locator(".ant-dropdown:not(.ant-dropdown-hidden)").locator("text=/^Video$/i").first
            if video_opt.is_visible(timeout=1500):
                video_opt.click(force=True)
            self.page.wait_for_timeout(800)
        except Exception as ex:
            logger.warning("Error applying revenue source filter for creator", error=str(ex))

        # 4. Tipe Akun: Mandiri
        try:
            logger.info("Setting Account Type: Mandiri")
            self.dismiss_overlays()
            ta = self.page.locator(".ant-dropdown-trigger:has-text('Tipe Akun')").first
            ta.scroll_into_view_if_needed()
            ta.click(force=True)
            self.page.wait_for_timeout(800)
            mandiri_opt = self.page.locator(".ant-dropdown:not(.ant-dropdown-hidden)").locator("text=/Mandiri|Independent/i").first
            if mandiri_opt.is_visible(timeout=1500):
                mandiri_opt.click(force=True)
            self.page.wait_for_timeout(800)
        except Exception as ex:
            logger.warning("Error applying account type filter for creator", error=str(ex))

        # 5. Submit / Kirim
        try:
            logger.info("Clicking Submit/Kirim for creator filters")
            self.dismiss_overlays()
            submit_btn = self.page.locator("button:has-text('Submit'), button:has-text('Kirim')").first
            if submit_btn.is_visible(timeout=1500) and submit_btn.is_enabled():
                submit_btn.click(force=True)
                self.page.wait_for_timeout(3500)
        except Exception as ex:
            logger.warning("Error clicking submit on creator filters", error=str(ex))

        self.dismiss_overlays()
        return True

    def scrape_creators(
        self,
        max_creators: Optional[int] = None,
        min_revenue: Optional[float] = 4000000.0,
        products_per_creator: int = 3,
        period_date: Optional[date] = None,
        cancel_check_cb: Optional[Callable[[], bool]] = None,
        checkpoint_cb: Optional[Callable[[List[Dict[str, Any]], int], None]] = None
    ) -> Dict[str, Any]:
        """
        Extracts creators from creator table and their top 3 products.
        Filters creators with revenue >= min_revenue (default 4,000,000 IDR or currency equivalent).
        If max_creators is provided (manual trigger), caps scraping at that number of creators.
        If max_creators is None (automatic scheduled scrape), runs until creator revenue drops below min_revenue.
        """
        items: List[Dict[str, Any]] = []
        total_creators_scanned = 0
        stop_scraping = False
        consecutive_below_min = 0
        page_number = 1

        # Try to expand page size to 50 if available
        try:
            size_trigger = self.page.locator('button[data-slot="select-trigger"]:has-text("Halaman"), button[data-slot="select-trigger"]:has-text("Page")').first
            if size_trigger.is_visible(timeout=1500):
                size_trigger.click()
                self.page.wait_for_timeout(500)
                opt_50 = self.page.locator('[role="option"]:has-text("50"), [data-slot="select-item"]:has-text("50")').first
                if opt_50.is_visible(timeout=1000):
                    opt_50.click()
                    self.page.wait_for_timeout(2000)
                    BaseScraper.pacing_page_delay()
        except Exception:
            pass

        # Tab for inspecting individual product details
        prod_tab = self.page.context.new_page()

        try:
            while not stop_scraping:
                if max_creators and total_creators_scanned >= max_creators:
                    break
                if cancel_check_cb and cancel_check_cb():
                    logger.info("Scrape cancelled by operator")
                    break

                self.dismiss_overlays()

                # Check for Cloudflare challenge and wait for operator in VNC
                if BaseScraper.is_challenge_active(self.page):
                    cleared, reason = BaseScraper.wait_for_challenge(
                        self.page, job_id=self.job_id, cancel_check_cb=cancel_check_cb
                    )
                    if not cleared:
                        stop_scraping = True
                        break

                rows = self.page.locator("tbody tr.group, tbody tr").all()
                if not rows:
                    logger.info("No creator rows found")
                    break

                logger.info("Found creator rows", count=len(rows), scanned_so_far=total_creators_scanned)

                # Process rows on current page
                for row in rows:
                    if max_creators and total_creators_scanned >= max_creators:
                        stop_scraping = True
                        break
                    if cancel_check_cb and cancel_check_cb():
                        stop_scraping = True
                        break

                    tds = row.locator("td").all()
                    if len(tds) < 3:
                        continue

                    # Extract creator revenue from td[2] (e.g. 'Rp19,01M', 'Rp4,5JT', 'Rp3,8JT')
                    creator_rev_raw = tds[2].inner_text().strip()
                    creator_rev_val, _ = NumberParser.parse_currency_amount(creator_rev_raw, self.country_code)

                    # Threshold check (min_revenue, default 50,000,000 IDR / 14,000 MYR / 110,000 THB)
                    if min_revenue and creator_rev_val is not None:
                        effective_min = min_revenue
                        is_myr = "RM" in creator_rev_raw.upper() or (self.country_code == "MY" and "RP" not in creator_rev_raw.upper())
                        is_thb = "THB" in creator_rev_raw.upper() or "฿" in creator_rev_raw or (self.country_code == "TH" and "RP" not in creator_rev_raw.upper())
                        if is_myr and effective_min >= 1_000_000:
                            effective_min = getattr(settings, "MIN_CREATOR_REVENUE_MYR", 14000.0)
                        elif is_thb and effective_min >= 1_000_000:
                            effective_min = getattr(settings, "MIN_CREATOR_REVENUE_THB", 110000.0)

                        if creator_rev_val < effective_min:
                            logger.info(
                                "Creator revenue below minimum threshold - stopping creator scrape",
                                revenue=creator_rev_val,
                                raw_revenue=creator_rev_raw,
                                threshold=effective_min,
                                country=self.country_code
                            )
                            stop_scraping = True
                            break
                    elif min_revenue and creator_rev_raw and creator_rev_raw not in ["-", "N/A", "null"]:
                        logger.warning(
                            "Could not parse creator revenue from table cell",
                            raw_revenue=creator_rev_raw,
                            country=self.country_code
                        )

                    # Extract creator name
                    creator_name_raw = tds[1].inner_text().strip()
                    creator_name = " ".join(creator_name_raw.split())
                    creator_log_name = creator_name.encode("ascii", "ignore").decode()

                    # Extract creator ID
                    creator_id = ""
                    img_c = tds[1].locator("div[style*='tiktok.creator'], img[src*='tiktok.creator']").first
                    if img_c.count() > 0:
                        style = img_c.get_attribute("style") or img_c.get_attribute("src") or ""
                        id_m = re.search(r"/tiktok\.creator/(\d+)/", style)
                        if id_m:
                            creator_id = id_m.group(1)

                    if not creator_id:
                        c_link = tds[1].locator("a").first
                        if c_link.count() > 0:
                            c_href = c_link.get_attribute("href") or ""
                            id_m = re.search(r"id=(\d+)", c_href)
                            if id_m:
                                creator_id = id_m.group(1)

                    total_creators_scanned += 1
                    logger.info("Opening creator details via click", creator=creator_log_name, creator_id=creator_id, revenue=creator_rev_raw)

                    # 1. Open creator detail page with filters preserved
                    detail_tab = None
                    try:
                        creator_target = tds[1].locator("span, .Component-Image, div").first
                        with self.page.context.expect_page(timeout=10000) as new_page_info:
                            creator_target.click()
                        detail_tab = new_page_info.value
                        detail_tab.wait_for_load_state("domcontentloaded")
                        detail_tab.wait_for_timeout(3000)
                    except Exception as click_ex:
                        logger.warning("Popup expect_page failed, falling back to direct URL with filters", creator=creator_log_name, error=str(click_ex))
                        date_str = str(period_date) if period_date else (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
                        full_c_url = f"{settings.KALODATA_BASE_URL.rstrip('/')}/creator/detail?id={creator_id}&language=id-ID&currency={self.currency_code}&region={self.country_code}&dateRange=%5B%22{date_str}%22%2C%22{date_str}%22%5D&cateValue=%5B%5B%22601152%22%2C%22842376%22%5D%5D"
                        detail_tab = self.page.context.new_page()
                        detail_tab.goto(full_c_url, wait_until="domcontentloaded", timeout=25000)
                        detail_tab.wait_for_timeout(3000)

                    try:
                        self.dismiss_overlays(detail_tab)

                        # Scroll down to Produk section
                        detail_tab.evaluate("""() => {
                            const th = Array.from(document.querySelectorAll('th')).find(t => t.innerText && t.innerText.includes('Info Produk'));
                            if (th) th.scrollIntoView();
                            else {
                                const leftProd = Array.from(document.querySelectorAll('div, li, span')).find(el => el.innerText && el.innerText.trim() === 'Produk');
                                if (leftProd) leftProd.click();
                                window.scrollTo(0, 1400);
                            }
                        }""")
                        detail_tab.wait_for_timeout(1500)
                        self.dismiss_overlays(detail_tab)

                        # 2. Extract top products from creator detail table
                        prods = detail_tab.evaluate(f"""() => {{
                            const th = Array.from(document.querySelectorAll('th')).find(t => t.innerText && t.innerText.includes('Info Produk'));
                            if (!th) return [];
                            const table = th.closest('table');
                            if (!table) return [];
                            const trs = table.querySelectorAll('tbody tr');
                            return Array.from(trs).slice(0, {products_per_creator}).map((r, i) => {{
                                const tds = r.querySelectorAll('td');
                                const rowKey = r.getAttribute('data-row-key') || '';
                                const imgEl = r.querySelector('div[style*=\"background-image\"], img');
                                const imgStyle = imgEl ? (imgEl.getAttribute('style') || imgEl.getAttribute('src') || '') : '';
                                const titleEl = tds[1] ? tds[1].querySelector('.line-clamp-2, div.font-medium, div') : null;
                                const name = titleEl ? titleEl.innerText.trim() : (tds[1] ? tds[1].innerText.trim() : '');
                                const rev = tds[2] ? tds[2].innerText.trim() : '';
                                const sold = tds[3] ? tds[3].innerText.trim() : '';
                                return {{
                                    index: i + 1,
                                    rowKey: rowKey,
                                    imgStyle: imgStyle,
                                    name: name,
                                    revenue: rev,
                                    sales: sold
                                }};
                            }});
                        }}""")

                        logger.info("Found top products for creator", creator=creator_log_name, count=len(prods))

                        # 3. For each product, extract product details (shop name & commission rate)
                        for prod in prods:
                            p_id = prod.get("rowKey") or ""
                            if not p_id:
                                m = re.search(r"/tiktok\.product/(\d+)/", prod.get("imgStyle", ""))
                                if m:
                                    p_id = m.group(1)

                            p_name = " ".join(prod.get("name", "").split())
                            p_rev_raw = prod.get("revenue", "")
                            p_sales_raw = prod.get("sales", "")
                            p_url = f"{settings.KALODATA_BASE_URL.rstrip('/')}/product/detail?id={p_id}&region={self.country_code}" if p_id else ""

                            rev_val, _ = NumberParser.parse_currency_amount(p_rev_raw, self.country_code)
                            sales_val = NumberParser.parse_integer_sales(p_sales_raw, self.country_code)

                            # Fetch shop name & commission from product detail
                            shop_name = ""
                            comm_raw = ""
                            comm_rate = None

                            if p_url:
                                for attempt in range(2):
                                    try:
                                        prod_tab.goto(p_url, wait_until="domcontentloaded", timeout=20000)
                                        prod_tab.wait_for_timeout(2000)
                                        self.dismiss_overlays(prod_tab)

                                        p_info = prod_tab.evaluate("""() => {
                                            let shop = '';
                                            // 1. Direct shop link (most reliable on modern Kalodata)
                                            const shopLinks = Array.from(document.querySelectorAll('a[href*="/shop/detail"], a[href*="/seller/detail"]'));
                                            for (const a of shopLinks) {
                                                const txt = a.innerText.trim();
                                                if (txt && !/^(?:detail|lihat|view)$/i.test(txt)) {
                                                    shop = txt;
                                                    break;
                                                }
                                            }
                                            // 2. Info card / section container
                                            if (!shop && shopLinks.length > 0) {
                                                const parent = shopLinks[0].closest('div[class*="bg-"], div[class*="rounded"], .section4, .infocard');
                                                if (parent) {
                                                    const titleEl = parent.querySelector('.font-bold, [class*="font-semibold"], [class*="text-ellipsis"]');
                                                    if (titleEl && !/^(?:detail|lihat|view)$/i.test(titleEl.innerText.trim())) {
                                                        shop = titleEl.innerText.trim();
                                                    }
                                                }
                                            }
                                            // 3. Info card by class fallback
                                            if (!shop) {
                                                const infoCard = document.querySelector('.infocard, .section4, [class*="bg-[#FAFAFA]"], .bg-base-faf');
                                                if (infoCard) {
                                                    const shopEl = infoCard.querySelector('.text-ellipsis1, .font-bold, div[class*="font-"]');
                                                    if (shopEl && !/^(?:detail|lihat|view)$/i.test(shopEl.innerText.trim())) {
                                                        shop = shopEl.innerText.trim();
                                                    }
                                                }
                                            }
                                            // 4. TreeWalker for Shop Information / Informasi Toko
                                            if (!shop) {
                                                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                                                let node;
                                                while (node = walker.nextNode()) {
                                                    const val = node.nodeValue.trim();
                                                    if (/^(?:Informasi Toko|Shop Information|Store Information|Brand & Shop)$/i.test(val)) {
                                                        const card = node.parentElement.closest('div[class*="rounded"], .section4, .infocard') || node.parentElement.parentElement;
                                                        if (card) {
                                                            const el = card.querySelector('a[href*="/shop/detail"], .text-ellipsis1, .font-bold');
                                                            if (el && !/^(?:detail|lihat|view)$/i.test(el.innerText.trim())) {
                                                                shop = el.innerText.trim();
                                                                break;
                                                            }
                                                        }
                                                    }
                                                }
                                            }

                                            // 5. Commission rate (multilingual: ID & EN)
                                            let comm = '';
                                            const m = document.body.innerText.match(/(?:Tingkat komisi|Commission rate|Commission|Komisi)[^\\d]*(\\d+(?:[\\.,]\\d+)?\\s*%)/i);
                                            if (m) comm = m[1];
                                            return { shop: shop, comm: comm };
                                        }""")
                                        shop_name = p_info.get("shop", "")
                                        if shop_name:
                                            first_line = shop_name.split("\n")[0].strip()
                                            shop_name = re.sub(r"\s*(?:Toko Lokal|Toko Cross Border|Lintas Batas|Local Shop|Cross Border)\s*$", "", first_line, flags=re.I).strip()
                                        comm_raw = p_info.get("comm", "")
                                        comm_rate = NumberParser.parse_commission_rate(comm_raw)
                                        break
                                    except Exception as p_ex:
                                        if attempt == 0:
                                            time.sleep(1.5)
                                        else:
                                            logger.warning("Error loading product detail for creator product", error=str(p_ex))

                            item_record = {
                                "creator_name": creator_name,
                                "creator_id": creator_id,
                                "creator_rank": total_creators_scanned,
                                "product_rank": prod.get("index", 1),
                                "source_product_id": p_id,
                                "product_name": p_name,
                                "shop_name": shop_name,
                                "product_url": p_url,
                                "revenue_raw": p_rev_raw,
                                "revenue_value": rev_val,
                                "sales_raw": p_sales_raw,
                                "sales_value": sales_val,
                                "commission_raw": comm_raw,
                                "commission_rate": comm_rate,
                                "currency_code": NumberParser.detect_currency(p_rev_raw or creator_rev_raw, default_country=self.country_code),
                                "country_code": self.country_code
                            }
                            items.append(item_record)

                        if checkpoint_cb:
                            checkpoint_cb(items, total_creators_scanned)

                    except Exception as c_ex:
                        logger.warning("Error processing creator detail", creator=creator_log_name, error=str(c_ex))
                    finally:
                        if detail_tab and not detail_tab.is_closed():
                            detail_tab.close()

                if stop_scraping:
                    break

                # Check pagination
                if max_creators is not None and total_creators_scanned >= max_creators:
                    break

                try:
                    self.dismiss_overlays()
                    next_selectors = [
                        f"button[data-slot='pagination-link']:text-is('{page_number + 1}')",
                        "button[data-slot='pagination-link'][aria-label*='berikutnya' i]",
                        "button[data-slot='pagination-link'][aria-label*='next' i]",
                        "nav button[aria-label*='berikutnya' i]",
                        "nav button[aria-label*='next' i]",
                        "nav ul li:last-child button",
                        "button[aria-label='Go to next page']",
                        "button.btn-next",
                        ".pagination-next",
                        "button:has-text('Next')"
                    ]
                    clicked_next = False
                    for n_sel in next_selectors:
                        btn = self.page.locator(n_sel).first
                        if btn.is_visible(timeout=1000):
                            if btn.is_disabled():
                                continue
                            aria_dis = btn.get_attribute("aria-disabled")
                            data_dis = btn.get_attribute("data-disabled")
                            if aria_dis == "true" or data_dis == "true":
                                continue
                            cls_tokens = set((btn.get_attribute("class") or "").split())
                            # Guard against Tailwind 'disabled:...' classes; only skip if actually disabled
                            if "pointer-events-none" in cls_tokens or "opacity-50" in cls_tokens or "disabled" in cls_tokens or "is-disabled" in cls_tokens:
                                continue
                            self.dismiss_overlays()
                            btn.click(force=True)
                            clicked_next = True
                            self.page.wait_for_timeout(2500)
                            BaseScraper.pacing_page_delay()
                            self.dismiss_overlays()
                            page_number += 1
                            break

                    if not clicked_next:
                        logger.info("No next page button found or disabled. Reached end of creator list.", total_scanned=total_creators_scanned, current_page=page_number)
                        break
                except Exception as p_ex:
                    logger.warning("Pagination error", error=str(p_ex))
                    break

        finally:
            if not prod_tab.is_closed():
                prod_tab.close()

        logger.info("Finished creator scraping", total_creators=total_creators_scanned, total_products=len(items))
        return {
            "items": items,
            "total_creators": total_creators_scanned
        }

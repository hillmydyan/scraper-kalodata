"""
Creator Scraper for Kalodata.
Scrapes creators and their top 3 best-selling products from https://www.kalodata.com/creator.
Filters:
- Tanggal: Kemarin
- Kategori: Bawahan Wanita
- Sumber Pendapatan: Video
- Tipe Akun: Mandiri
"""

import re
import sys
import time
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Callable
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
    def __init__(self, page: Page, country_code: str = "ID"):
        self.page = page
        self.country_code = country_code.upper()
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

    def apply_filters(self) -> bool:
        """
        Applies:
        1. Tanggal: Kemarin
        2. Kategori: Bawahan Wanita
        3. Sumber Pendapatan: Video
        4. Tipe Akun: Mandiri
        5. Submit / Kirim
        """
        logger.info("Applying creator filters", country=self.country_code)
        self.dismiss_overlays()

        # 1. Date: Kemarin
        try:
            logger.info("Setting Date: Kemarin")
            dt = self.page.locator("div.cursor-pointer:has-text('Tanggal')").first
            dt.click(force=True)
            self.page.wait_for_timeout(800)
            kemarin_btn = self.page.locator(".ant-popover:not(.ant-popover-hidden)").locator("text=/Yesterday|^Kemarin/i").first
            if kemarin_btn.is_visible(timeout=2000):
                kemarin_btn.click(force=True)
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

                    # Threshold check (min_revenue, default 4,000,000 IDR)
                    if min_revenue and creator_rev_val is not None:
                        effective_min = min_revenue
                        is_myr = "RM" in creator_rev_raw.upper() or (self.country_code == "MY" and "RP" not in creator_rev_raw.upper())
                        is_thb = "THB" in creator_rev_raw.upper() or "฿" in creator_rev_raw or (self.country_code == "TH" and "RP" not in creator_rev_raw.upper())
                        if is_myr:
                            effective_min = min_revenue / 3600.0  # ~1100 MYR
                        elif is_thb:
                            effective_min = min_revenue / 460.0   # ~8700 THB

                        if creator_rev_val < effective_min:
                            logger.info(
                                "Creator revenue below minimum threshold - stopping creator scrape",
                                revenue=creator_rev_val,
                                raw_revenue=creator_rev_raw,
                                threshold=effective_min,
                                creators_scanned=total_creators_scanned
                            )
                            stop_scraping = True
                            break

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
                                try:
                                    prod_tab.goto(p_url, wait_until="domcontentloaded", timeout=20000)
                                    prod_tab.wait_for_timeout(2000)
                                    self.dismiss_overlays(prod_tab)

                                    p_info = prod_tab.evaluate("""() => {
                                        let shop = '';
                                        const infoCard = document.querySelector('.infocard, .section4');
                                        if (infoCard) {
                                            const shopEl = infoCard.querySelector('.bg-base-faf .text-ellipsis1, .bg-base-faf .font-bold, .text-ellipsis1');
                                            if (shopEl) shop = shopEl.innerText.trim();
                                        }
                                        if (!shop) {
                                            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                                            let node;
                                            while (node = walker.nextNode()) {
                                                if (node.nodeValue.trim() === 'Informasi Toko') {
                                                    const card = node.parentElement.closest('.section4, .infocard') || node.parentElement.parentElement.parentElement;
                                                    if (card) {
                                                        const el = card.querySelector('.bg-base-faf .text-ellipsis1, .text-ellipsis1');
                                                        if (el) shop = el.innerText.trim();
                                                    }
                                                    break;
                                                }
                                            }
                                        }
                                        let comm = '';
                                        const m = document.body.innerText.match(/Tingkat komisi[^\\d]*(\\d+(?:[\\.,]\\d+)?\\s*%)/i);
                                        if (m) comm = m[1];
                                        return { shop: shop, comm: comm };
                                    }""")
                                    shop_name = p_info.get("shop", "")
                                    comm_raw = p_info.get("comm", "")
                                    comm_rate = NumberParser.parse_commission_rate(comm_raw)
                                except Exception as p_ex:
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
                                "currency_code": self.currency_code,
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
                    next_btn = self.page.locator("button[aria-label='Go to next page'], button.btn-next, .pagination-next, button:has-text('Next')").first
                    if next_btn.is_visible(timeout=1500) and next_btn.is_enabled():
                        next_btn.click(force=True)
                        self.page.wait_for_timeout(2500)
                        BaseScraper.pacing_page_delay()
                    else:
                        break
                except Exception:
                    break

        finally:
            if not prod_tab.is_closed():
                prod_tab.close()

        logger.info("Finished creator scraping", total_creators=total_creators_scanned, total_products=len(items))
        return {
            "items": items,
            "total_creators": total_creators_scanned
        }

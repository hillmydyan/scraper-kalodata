"""
Product list table scraper, pagination, checkpointing, and validation.
Follows rules in PRD §6.5, §6.8, §6.10, and §6.11.
"""

from typing import List, Dict, Any, Optional, Callable, Tuple
import structlog
from playwright.sync_api import Page

from app.config import settings, sel, get_country_config
from app.scrapers.base import BaseScraper
from app.scrapers.kalodata.parsers import NumberParser
from app.scrapers.kalodata.product_detail import ProductDetailScraper

logger = structlog.get_logger(__name__)


class ProductListScraper:
    def __init__(self, page: Page, country_code: str, job_id: Optional[str] = None):
        self.page = page
        self.country_code = country_code
        self.job_id = job_id
        self.country_cfg = get_country_config(country_code)
        self.currency_code = self.country_cfg.get("currency_code", "IDR")

    def dismiss_overlays(self) -> None:
        """Removes blocking marketing/promo/VIP upgrade overlays."""
        try:
            self.page.evaluate(
                "() => document.querySelectorAll('.ant-modal-root, .ant-modal-mask, .ant-modal-wrap, .ModalFeatureMemberWrapper, [class*=\"vip-modal\"], [class*=\"upgrade-modal\"]').forEach(el => el.remove())"
            )
        except Exception:
            pass

    def scrape_products(
        self,
        max_limit: Optional[int] = 400,
        min_sales: Optional[int] = 150,
        max_sales: Optional[int] = None,
        checkpoint_cb: Optional[Callable[[List[Dict[str, Any]], int], None]] = None,
        cancel_check_cb: Optional[Callable[[], bool]] = None,
        revenue_source_method: str = "product_filter"
    ) -> Dict[str, Any]:
        """
        Iterates product table rows up to max_limit (hard-capped at MAX_PRODUCTS_PER_COUNTRY, default 400).
        Saves checkpoints and validates data per row.
        """
        # Hard cap for products: maximum 400 rows
        product_hard_cap = getattr(settings, "MAX_PRODUCTS_PER_COUNTRY", 400) or 400
        if max_limit is None or max_limit <= 0 or max_limit > product_hard_cap:
            max_limit = product_hard_cap

        items: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        seen_product_ids = set()
        consecutive_stale_pages = 0
        is_truncated = False

        self.dismiss_overlays()

        # Wait for product table or rows
        tbl_sel = sel("product_table")
        for s in [tbl_sel["primary"]] + tbl_sel.get("fallbacks", []):
            try:
                self.page.locator(s).first.wait_for(timeout=10000)
                break
            except Exception:
                pass

        # Try to expand page size to 50 if available
        try:
            page_size_trigger = self.page.locator('button[data-slot="select-trigger"]:has-text("Halaman"), button[data-slot="select-trigger"]:has-text("Page"), .el-pagination__sizes').first
            if page_size_trigger.is_visible(timeout=1500):
                page_size_trigger.click()
                self.page.wait_for_timeout(500)
                opt_50 = self.page.locator('[role="option"]:has-text("50"), [data-slot="select-item"]:has-text("50"), .el-select-dropdown__item:has-text("50")').first
                if opt_50.is_visible(timeout=1000):
                    opt_50.click()
                    self.page.wait_for_timeout(2000)
                    BaseScraper.pacing_page_delay()
        except Exception:
            pass

        detail_tab = None
        detail_scraper = None

        page_number = 1
        total_scanned = 0
        consecutive_rejects = 0
        stop_scraping = False

        while not stop_scraping and len(items) < max_limit:
            self.dismiss_overlays()

            # Check for Cloudflare challenge and wait for operator if needed
            if BaseScraper.is_challenge_active(self.page):
                cleared, reason = BaseScraper.wait_for_challenge(
                    self.page, job_id=self.job_id, cancel_check_cb=cancel_check_cb
                )
                if not cleared:
                    break

            # Check cancellation flag (§8.6)
            if cancel_check_cb and cancel_check_cb():
                logger.info("Scrape job cancellation requested by operator")
                break

            # Check for Kalodata tier / membership limit modal (e.g. 500 rows limit reached)
            try:
                vip_modal = self.page.locator(".ant-modal:has-text('Keanggotaan Diperlukan'), div[role='dialog']:has-text('Enterprise')").first
                if vip_modal.is_visible(timeout=500):
                    logger.info("Kalodata membership row limit reached (Keanggotaan Diperlukan), stopping product scrape", total_scanned=total_scanned, items_saved=len(items))
                    try:
                        vip_modal.locator(".ant-modal-close, button[aria-label='Close']").first.click(force=True)
                    except Exception:
                        pass
                    break
            except Exception:
                pass

            # Fetch row locators
            row_sel = sel("product_table_row")
            rows = []
            for s in [row_sel["primary"]] + row_sel.get("fallbacks", []):
                try:
                    found = self.page.locator(s).all()
                    if found:
                        rows = found
                        break
                except Exception:
                    pass

            if not rows:
                logger.info("No more product rows found on page", page=page_number)
                break

            logger.info("Processing rows on page", page=page_number, count=len(rows))
            new_items_on_page = 0

            for row_idx, row in enumerate(rows):
                if max_limit is not None and len(items) >= max_limit:
                    is_truncated = True
                    stop_scraping = True
                    break

                if cancel_check_cb and cancel_check_cb():
                    stop_scraping = True
                    break

                total_scanned += 1
                row_text = row.inner_text().strip()
                if not row_text:
                    continue

                # Extract cells/links from row
                extracted = self._extract_row_data(row)
                if not extracted:
                    rejected.append({
                        "row_index": total_scanned,
                        "reason": "EMPTY_OR_UNPARSEABLE_ROW",
                        "raw": {"text": row_text}
                    })
                    consecutive_rejects += 1
                    continue

                # Filter products with sales < min_sales (e.g. sales >= 50 passes, sales < 50 rejected)
                sales_val = extracted.get("sales_value")
                if min_sales is not None:
                    if sales_val is None or sales_val < min_sales:
                        rejected.append({
                            "row_index": total_scanned,
                            "reason": f"SALES_BELOW_MIN_{min_sales}",
                            "raw": extracted
                        })
                        consecutive_rejects += 1
                        logger.info(
                            "Skipping product with sales < min_sales",
                            sales=sales_val,
                            raw_sales=extracted.get("sales_raw"),
                            min_sales=min_sales,
                            product_name=extracted.get("product_name")
                        )
                        # Early exit guard: if 40 consecutive rows on initial pages fail, stop early
                        if len(items) == 0 and consecutive_rejects >= 40:
                            logger.info(
                                "Early exit: 40 consecutive products below min_sales on initial pages. Stopping scrape to avoid hitting tier limit.",
                                total_scanned=total_scanned,
                                min_sales=min_sales
                            )
                            stop_scraping = True
                            break
                        elif len(items) > 0 and consecutive_rejects >= 60:
                            logger.info(
                                "Early exit: 60 consecutive products below min_sales after saving items. Stopping scrape.",
                                total_scanned=total_scanned,
                                items_saved=len(items)
                            )
                            stop_scraping = True
                            break
                        continue

                # Filter products with sales > max_sales (if upper bound specified)
                if max_sales is not None and max_sales > 0 and sales_val is not None and sales_val > max_sales:
                    rejected.append({
                        "row_index": total_scanned,
                        "reason": f"SALES_ABOVE_MAX_{max_sales}",
                        "raw": extracted
                    })
                    consecutive_rejects += 1
                    logger.info(
                        "Skipping product with sales > max_sales",
                        sales=sales_val,
                        raw_sales=extracted.get("sales_raw"),
                        max_sales=max_sales,
                        product_name=extracted.get("product_name")
                    )
                    continue

                # Open detail tab to select 1 video and extract video breakdown
                if extracted.get("product_url"):
                    try:
                        if detail_tab is None or detail_tab.is_closed():
                            detail_tab = self.page.context.new_page()
                            detail_scraper = ProductDetailScraper(detail_tab, self.country_code)

                        detail_info = detail_scraper.extract_detail_data(
                            extracted["product_url"],
                            revenue_source_method=revenue_source_method
                        )

                        if not detail_info.get("include_product", True):
                            rejected.append({
                                "row_index": total_scanned,
                                "reason": "NO_VIDEO_REVENUE",
                                "raw": extracted
                            })
                            consecutive_rejects += 1
                            continue

                        if detail_info.get("shop_name"):
                            extracted["shop_name"] = detail_info["shop_name"]
                        if detail_info.get("commission_rate") is not None and extracted.get("commission_rate") is None:
                            extracted["commission_rate"] = detail_info["commission_rate"]
                            extracted["commission_raw"] = detail_info.get("commission_raw", "")
                        if not extracted.get("video_url") and detail_info.get("video_url"):
                            extracted["video_url"] = detail_info.get("video_url")
                            extracted["video_url_type"] = detail_info.get("video_url_type", "tiktok")
                            extracted["video_selection_method"] = detail_info.get("video_selection_method", "top_revenue")
                    except Exception as e:
                        logger.warning("Error fetching detail for row", error=str(e))
                    finally:
                        # Clean up any extra tabs/popups spawned by Kalodata interactions
                        try:
                            for p in self.page.context.pages:
                                if p != self.page and p != detail_tab and not p.is_closed():
                                    p.close()
                        except Exception:
                            pass

                # Validate data (§6.10)
                is_valid, reason = self._validate_row(extracted, min_sales=min_sales, max_sales=max_sales)
                if not is_valid:
                    rejected.append({
                        "row_index": total_scanned,
                        "reason": reason,
                        "raw": extracted
                    })
                    consecutive_rejects += 1
                    continue

                # Check duplicate within this run
                prod_id = extracted.get("source_product_id")
                if prod_id and prod_id in seen_product_ids:
                    continue
                if prod_id:
                    seen_product_ids.add(prod_id)

                # Row accepted
                consecutive_rejects = 0
                new_items_on_page += 1
                items.append(extracted)

                # Checkpoint callback (§6.5 no. 9)
                if checkpoint_cb and len(items) % settings.CHECKPOINT_EVERY == 0:
                    checkpoint_cb(items, total_scanned)

                # Immediately stop if max_limit (e.g. 400) is reached
                if len(items) >= max_limit:
                    is_truncated = True
                    stop_scraping = True
                    break

            if stop_scraping:
                break

            # Guard against stale pagination (clicking next but remaining on same page)
            if len(rows) > 0 and new_items_on_page == 0:
                consecutive_stale_pages += 1
                if consecutive_stale_pages >= 2:
                    logger.info("Pagination stale: no new products found on 2 consecutive pages, stopping.", total_scanned=total_scanned, items_saved=len(items))
                    break
            else:
                consecutive_stale_pages = 0

            # Pagination: look for 'Next' button
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
                        BaseScraper.pacing_page_delay()
                        self.page.wait_for_timeout(2500)
                        self.dismiss_overlays()
                        page_number += 1
                        break

                if not clicked_next:
                    logger.info("Next page button disabled or absent. Reached last page.", total_scanned=total_scanned, current_page=page_number)
                    break
            except Exception as p_ex:
                logger.info("Could not navigate to next page.", error=str(p_ex))
                break

        if detail_tab and not detail_tab.is_closed():
            detail_tab.close()

        # Final checkpoint callback
        if checkpoint_cb:
            checkpoint_cb(items, total_scanned)

        return {
            "items": items,
            "rejected": rejected,
            "total_scanned": total_scanned,
            "is_truncated": is_truncated
        }

    def _extract_row_data(self, row) -> Optional[Dict[str, Any]]:
        """Extracts fields from a single table row using verified Kalodata DOM."""
        try:
            import re
            import hashlib

            # Extract row cells via evaluate for maximum performance and accuracy
            cell_data = row.evaluate("""(r) => {
                const tds = Array.from(r.querySelectorAll('td'));
                if (tds.length < 2) return null;
                
                // Rank
                const rank = tds[0].innerText.trim();
                
                // Cell 1: Product Info (Name, Image Style)
                const cell1 = tds[1];
                const imgEl = cell1.querySelector('div[style*=\"background-image\"], img');
                const styleOrSrc = imgEl ? (imgEl.getAttribute('style') || imgEl.getAttribute('src') || '') : '';
                
                // Get title element specifically to avoid merging badge or price
                const titleEl = cell1.querySelector('.line-clamp-2, div.font-medium');
                let name = titleEl ? titleEl.innerText.trim() : '';
                if (!name) {
                    const clone = cell1.cloneNode(true);
                    clone.querySelectorAll('button, [data-slot=\"badge\"]').forEach(b => b.remove());
                    const lines = clone.innerText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                    name = lines.length > 0 ? lines[0] : '';
                }
                const shop = '';
                
                // Cell 2: Revenue
                const rev = tds.length > 2 ? tds[2].innerText.trim() : '';
                
                // Cell 5: Item Sold
                const sold = tds.length > 5 ? tds[5].innerText.trim() : '';
                
                // Cell 6: Video GMV Tertinggi (Video Terlaris)
                let videoStyle = '';
                if (tds.length > 6) {
                    const vCover = tds[6].querySelector('.Layout-VideoCover, div[style*="tiktok.video"]');
                    videoStyle = vCover ? (vCover.getAttribute('style') || vCover.getAttribute('src') || '') : '';
                }

                // Cell 10: Tingkat komisi
                const commission = tds.length > 10 ? tds[10].innerText.trim() : '';
                
                // Check if any link exists
                const a = r.querySelector('a');
                const linkHref = a ? a.href : '';
                
                return {
                    rank: rank,
                    name: name,
                    shop: shop,
                    styleOrSrc: styleOrSrc,
                    revenue: rev,
                    sold: sold,
                    videoStyle: videoStyle,
                    commission: commission,
                    linkHref: linkHref,
                    fullText: r.innerText
                };
            }""")

            if not cell_data:
                return None

            prod_name = cell_data.get("name") or "Product"
            # Strip trailing currency or garbage from name if merged
            prod_name = re.sub(r"(?:Rp|RM|฿|\$)\s*[\*0-9\.,\-RBJTMKk]+$", "", prod_name).strip()
            
            # Heuristic shop name from title bracket e.g. [ Tara id ] or prefix before dash
            shop_name = cell_data.get("shop") or ""
            if not shop_name:
                shop_match = re.search(r"^\[\s*([^\]]+?)\s*\]", prod_name)
                if shop_match:
                    shop_name = shop_match.group(1).strip()
                elif "-" in prod_name and len(prod_name.split("-")[0].strip()) < 30:
                    first_part = prod_name.split("-")[0].strip()
                    if not any(kw in first_part.lower() for kw in ["celana", "rok", "jeans", "bawahan", "kulot", "loose", "wide"]):
                        shop_name = first_part

            # Extract source product ID from image CDN URL: /tiktok.product/{id}/
            style_str = cell_data.get("styleOrSrc") or ""
            id_match = re.search(r"/tiktok\.product/(\d+)/", style_str)
            if not id_match:
                id_match = re.search(r"/(\d{15,30})[/\.]", style_str)

            if id_match:
                source_prod_id = id_match.group(1)
            elif cell_data.get("linkHref") and re.search(r"id=(\d+)", cell_data["linkHref"]):
                source_prod_id = re.search(r"id=(\d+)", cell_data["linkHref"]).group(1)
            else:
                # Search numeric pattern in row text
                id_search = re.search(r"\b(\d{15,25})\b", cell_data.get("fullText", ""))
                if id_search:
                    source_prod_id = id_search.group(1)
                else:
                    source_prod_id = str(int(hashlib.md5(prod_name.encode()).hexdigest()[:15], 16))

            prod_url = f"{settings.KALODATA_BASE_URL.rstrip('/')}/product/detail?id={source_prod_id}&region={self.country_code}"

            rev_raw = cell_data.get("revenue") or ""
            sales_raw = cell_data.get("sold") or ""
            comm_raw = cell_data.get("commission") or ""

            # Video from Cell 6
            video_url = None
            video_selection_method = "none"
            v_style = cell_data.get("videoStyle") or ""
            vm = re.search(r"/tiktok\.video/(\d+)/", v_style)
            if vm:
                video_url = f"https://www.tiktok.com/@/video/{vm.group(1)}"
                video_selection_method = "top_revenue"

            rev_val, rev_abbr = NumberParser.parse_currency_amount(rev_raw, self.country_code)
            sales_val = NumberParser.parse_integer_sales(sales_raw, self.country_code)
            comm_rate = NumberParser.parse_commission_rate(comm_raw)

            return {
                "source_product_id": source_prod_id,
                "product_name": prod_name,
                "shop_name": shop_name,
                "product_url": prod_url,
                "revenue_raw": rev_raw,
                "revenue_value": rev_val,
                "revenue_is_abbreviated": rev_abbr,
                "sales_raw": sales_raw,
                "sales_value": sales_val,
                "commission_raw": comm_raw,
                "commission_rate": comm_rate,
                "currency_code": NumberParser.detect_currency(rev_raw, default_country=self.country_code),
                "country_code": self.country_code,
                "video_url": video_url,
                "video_url_type": "tiktok",
                "video_selection_method": video_selection_method
            }
        except Exception as e:
            logger.warning("Error parsing table row", error=str(e))
            return None

    def _validate_row(
        self,
        row: Dict[str, Any],
        min_sales: Optional[int] = 150,
        max_sales: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Validates row according to PRD §6.10."""
        if not row.get("source_product_id"):
            return False, "MISSING_PRODUCT_ID"
        if not row.get("product_name"):
            return False, "MISSING_PRODUCT_NAME"

        rev = row.get("revenue_value")
        if rev is not None and rev < 0:
            return False, "INVALID_REVENUE_NEGATIVE"

        sales = row.get("sales_value")
        if sales is not None and sales < 0:
            return False, "INVALID_SALES_NEGATIVE"
        if min_sales is not None and (sales is None or sales < min_sales):
            return False, f"SALES_BELOW_MIN_{min_sales}"
        if max_sales is not None and max_sales > 0 and (sales is not None and sales > max_sales):
            return False, f"SALES_ABOVE_MAX_{max_sales}"

        comm = row.get("commission_rate")
        if comm is not None and (comm < 0.0 or comm > 1.0):
            return False, "INVALID_COMMISSION_RANGE"

        return True, ""

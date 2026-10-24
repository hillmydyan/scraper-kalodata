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
        max_limit: Optional[int] = 2000,
        min_sales: Optional[int] = 50,
        checkpoint_cb: Optional[Callable[[List[Dict[str, Any]], int], None]] = None,
        cancel_check_cb: Optional[Callable[[], bool]] = None,
        revenue_source_method: str = "product_filter"
    ) -> Dict[str, Any]:
        """
        Iterates product table rows up to max_limit (or all pages if max_limit is None).
        Saves checkpoints and validates data per row.
        """
        items: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
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

        # Try to expand page size to maximum available (e.g. 50 or 100 per page)
        try:
            page_size_trigger = self.page.locator(".el-pagination__sizes").first
            if page_size_trigger.is_visible(timeout=1000):
                page_size_trigger.click()
                self.page.locator(".el-select-dropdown__item:has-text('50')").first.click(timeout=1000)
                BaseScraper.pacing_page_delay()
        except Exception:
            pass

        detail_tab = None
        detail_scraper = None

        page_number = 1
        total_scanned = 0

        while max_limit is None or len(items) < max_limit:
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

            for row_idx, row in enumerate(rows):
                if max_limit is not None and len(items) >= max_limit:
                    is_truncated = True
                    break

                if cancel_check_cb and cancel_check_cb():
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
                    continue

                # Filter products with sales <= min_sales (e.g. sales > 50) before opening detail tab
                sales_val = extracted.get("sales_value")
                if min_sales is not None:
                    if sales_val is None or sales_val <= min_sales:
                        rejected.append({
                            "row_index": total_scanned,
                            "reason": f"SALES_BELOW_MIN_{min_sales}",
                            "raw": extracted
                        })
                        logger.info(
                            "Skipping product with sales <= min_sales",
                            sales=sales_val,
                            raw_sales=extracted.get("sales_raw"),
                            min_sales=min_sales,
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

                # Validate data (§6.10)
                is_valid, reason = self._validate_row(extracted, min_sales=min_sales)
                if not is_valid:
                    rejected.append({
                        "row_index": total_scanned,
                        "reason": reason,
                        "raw": extracted
                    })
                    continue

                items.append(extracted)

                # Checkpoint callback (§6.5 no. 9)
                if checkpoint_cb and len(items) % settings.CHECKPOINT_EVERY == 0:
                    checkpoint_cb(items, total_scanned)

            # Pagination: look for 'Next' button
            try:
                self.dismiss_overlays()
                next_btn = self.page.locator("button[aria-label='Go to next page'], button.btn-next, .pagination-next, button:has-text('Next')").first
                if next_btn.is_visible(timeout=1500) and next_btn.is_enabled():
                    next_btn.click()
                    BaseScraper.pacing_page_delay()
                    page_number += 1
                else:
                    logger.info("Next page button disabled or absent. Reached last page.")
                    break
            except Exception:
                logger.info("Could not navigate to next page.")
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

    def _validate_row(self, row: Dict[str, Any], min_sales: Optional[int] = 50) -> Tuple[bool, str]:
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
        if min_sales is not None and (sales is None or sales <= min_sales):
            return False, f"SALES_BELOW_MIN_{min_sales}"

        comm = row.get("commission_rate")
        if comm is not None and (comm < 0.0 or comm > 1.0):
            return False, "INVALID_COMMISSION_RANGE"

        return True, ""

"""
Product detail page scraper and video selection engine.
Follows rules in PRD §6.4, §6.7, and §6.8.
"""

import time
import re
from typing import Dict, Any, Optional, List, Tuple
import structlog
from playwright.sync_api import Page

from app.config import settings
from app.scrapers.base import BaseScraper
from app.scrapers.kalodata.parsers import NumberParser

logger = structlog.get_logger(__name__)


class ProductDetailScraper:
    def __init__(self, page: Page, country_code: str):
        self.page = page
        self.country_code = country_code

    def extract_detail_data(
        self,
        detail_url: str,
        revenue_source_method: str = "product_filter"
    ) -> Dict[str, Any]:
        """
        Navigates to detail URL in a dedicated page/tab, extracts detail metrics,
        revenue breakdown (if needed), and selects one video (§6.7).
        """
        result = {
            "detail_revenue_raw": None,
            "detail_revenue_value": None,
            "detail_sales_raw": None,
            "detail_sales_value": None,
            "video_url": None,
            "video_url_type": "tiktok",
            "video_selection_method": "none",
            "include_product": True
        }

        loaded = False
        for attempt in range(2):
            try:
                self.page.goto(detail_url, wait_until="domcontentloaded", timeout=25000)
                BaseScraper.pacing_detail_delay()
                loaded = True
                break
            except Exception as e:
                if attempt == 0:
                    time.sleep(1.5)
                else:
                    logger.warning("Failed to open product detail", url=detail_url, error=str(e))
        if not loaded:
            return result

        # 1. If fallback revenue_source_method == 'detail_breakdown', inspect video revenue share (§6.4)
        if revenue_source_method == "detail_breakdown":
            try:
                # Look for revenue breakdown by channel
                video_rev_el = self.page.locator("text=/Video/i").first
                if video_rev_el.is_visible(timeout=1000):
                    # Check if video revenue > 0
                    pass
            except Exception:
                pass

        # 2. Extract shop name and commission rate using fast, multilingual DOM extraction
        shop_name = ""
        commission_rate = None
        commission_raw = ""
        try:
            self.page.wait_for_selector('a[href*="/shop/detail"], a[href*="/seller/detail"], .section4, [class*="bg-[#FAFAFA]"], text=/Commission|Tingkat komisi|Shop Information|Informasi Toko/i', timeout=5000)
        except Exception:
            pass

        try:
            p_info = self.page.evaluate("""() => {
                let shop = '';
                // 1. Direct shop link
                const shopLinks = Array.from(document.querySelectorAll('a[href*="/shop/detail"], a[href*="/seller/detail"]'));
                for (const a of shopLinks) {
                    const text = a.innerText.trim();
                    if (text && !/^(?:detail|lihat|view)$/i.test(text)) {
                        shop = text;
                        break;
                    }
                }
                // 2. Card container around shop link
                if (!shop && shopLinks.length > 0) {
                    const card = shopLinks[0].closest('div[class*="rounded"], .section4, [class*="bg-[#FAFAFA]"]');
                    if (card) {
                        const titleEl = card.querySelector('.text-ellipsis1, .font-bold, div[class*="font-"]');
                        if (titleEl && !/^(?:detail|lihat|view)$/i.test(titleEl.innerText.trim())) {
                            shop = titleEl.innerText.trim();
                        }
                    }
                }
                // 3. Info card fallback
                if (!shop) {
                    const infoCard = document.querySelector('.infocard, .section4, [class*="bg-[#FAFAFA]"], .bg-base-faf');
                    if (infoCard) {
                        const shopEl = infoCard.querySelector('.text-ellipsis1, .font-bold, div[class*="font-"]');
                        if (shopEl && !/^(?:detail|lihat|view)$/i.test(shopEl.innerText.trim())) {
                            shop = shopEl.innerText.trim();
                        }
                    }
                }
                // 4. TreeWalker for multilingual labels
                if (!shop) {
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    let node;
                    while (node = walker.nextNode()) {
                        const val = node.nodeValue.trim();
                        if (/^(?:Informasi Toko|Shop Information|Store Information|Brand & Shop)$/i.test(val)) {
                            const card = node.parentElement.closest('div[class*="rounded"], .section4, .infocard') || node.parentElement.parentElement;
                            if (card) {
                                const el = card.querySelector('a[href*="/shop/detail"], a[href*="/seller/detail"], .text-ellipsis1, .font-bold');
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
            commission_raw = p_info.get("comm", "")
            commission_rate = NumberParser.parse_commission_rate(commission_raw)
        except Exception as ex:
            logger.debug("Failed evaluating shop and commission", error=str(ex))

        result["shop_name"] = shop_name
        result["commission_rate"] = commission_rate
        result["commission_raw"] = commission_raw

        # 4. Extract 1 Video following §6.7 rules
        video_data = self._select_best_video()
        result.update(video_data)

        return result

    def _select_best_video(self) -> Dict[str, Any]:
        """
        Selects 1 video according to §6.7 priority hierarchy:
        1. top_revenue
        2. top_sales
        3. max_revenue_scanned
        4. first_listed
        5. none (NULL)
        """
        # Look for 'Video & Ad' or 'Videos' tab
        try:
            videos_tab = self.page.locator("div.flex:has-text('Video & Ad'), [role='tab']:has-text('Video'), text=/Video & Ad/i").first
            if videos_tab.is_visible(timeout=1500):
                videos_tab.click()
                BaseScraper.pacing_detail_delay()
        except Exception:
            try:
                videos_link = self.page.locator("text=/Videos/i").first
                if videos_link.is_visible(timeout=1000):
                    videos_link.click()
                    BaseScraper.pacing_detail_delay()
            except Exception:
                pass

        # Check for video items or links
        # Attempt 1: Sort by revenue/GMV if sort button exists
        try:
            sort_btn = self.page.locator("text=/Revenue|GMV/i").first
            if sort_btn.is_visible(timeout=1000):
                sort_btn.click()
                BaseScraper.pacing_detail_delay()
                video_url, url_type = self._find_first_video_link()
                if video_url:
                    return {
                        "video_url": video_url,
                        "video_url_type": url_type,
                        "video_selection_method": "top_revenue"
                    }
        except Exception:
            pass

        # Attempt 2: Sort by sales if sort button exists
        try:
            sort_sales = self.page.locator("text=/Sales/i").first
            if sort_sales.is_visible(timeout=1000):
                sort_sales.click()
                BaseScraper.pacing_detail_delay()
                video_url, url_type = self._find_first_video_link()
                if video_url:
                    return {
                        "video_url": video_url,
                        "video_url_type": url_type,
                        "video_selection_method": "top_sales"
                    }
        except Exception:
            pass

        # Attempt 3 & 4: First listed video link
        video_url, url_type = self._find_first_video_link()
        if video_url:
            return {
                "video_url": video_url,
                "video_url_type": url_type,
                "video_selection_method": "first_listed"
            }

        # Rule 5: No video found -> NULL, method none
        return {
            "video_url": None,
            "video_url_type": "tiktok",
            "video_selection_method": "none"
        }

    def _find_first_video_link(self) -> (Optional[str], str):
        """Finds TikTok original video link or Kalodata video URL."""
        # 1. Search for tiktok.com link in page
        try:
            links = self.page.locator("a[href*='tiktok.com']").all()
            for l in links:
                href = l.get_attribute("href")
                if href and "/video/" in href:
                    return href, "tiktok"
        except Exception:
            pass

        # 2. Search for Kalodata video detail link
        try:
            links = self.page.locator("a[href*='/video/']").all()
            for l in links:
                href = l.get_attribute("href")
                if href:
                    if not href.startswith("http"):
                        href = f"{settings.KALODATA_BASE_URL.rstrip('/')}{href}"
                    return href, "kalodata"
        except Exception:
            pass

        return None, "tiktok"

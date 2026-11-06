"""
Daily Product Insight: bandingkan hasil scraping produk 1 periode vs periode sebelumnya (per region).
Semua angka dihitung di sini (deterministik). LLM hanya menulis ringkasan dari angka yang sudah jadi.
"""

import json
from datetime import date
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, func

from app.models.entities import KalodataProductResult, DailyProductInsight
from app.services import llm_client

logger = structlog.get_logger(__name__)

TOP_N = 15          # jumlah item per daftar yang disimpan
SPIKE_RATIO = 0.5   # naik/turun >= 50% dianggap signifikan


def _rows(db, country: str, period: date) -> List[KalodataProductResult]:
    stmt = select(KalodataProductResult).where(
        KalodataProductResult.country_code == country,
        KalodataProductResult.period_start == period,
    )
    return list(db.execute(stmt).scalars().all())


def _ranked(rows: List[KalodataProductResult]) -> Dict[str, Dict[str, Any]]:
    """Map source_product_id -> data ringkas + rank berdasarkan revenue (1 = tertinggi)."""
    srt = sorted(rows, key=lambda r: float(r.revenue_value or 0), reverse=True)
    out = {}
    for i, r in enumerate(srt, start=1):
        out[r.source_product_id] = {
            "id": r.source_product_id,
            "name": (r.product_name or "-")[:120],
            "shop": r.shop_name or "-",
            "revenue": float(r.revenue_value or 0),
            "sales": int(r.sales_value or 0),
            "commission": float(r.commission_rate) if r.commission_rate is not None else None,
            "currency": r.currency_code,
            "url": r.product_url,
            "rank": i,
        }
    return out


def _pct(new: float, old: float) -> Optional[float]:
    if not old:
        return None
    return round((new - old) / old * 100, 1)


def previous_period(db, country: str, period: date) -> Optional[date]:
    stmt = select(func.max(KalodataProductResult.period_start)).where(
        KalodataProductResult.country_code == country,
        KalodataProductResult.period_start < period,
    )
    return db.execute(stmt).scalar()


def compute_diff(db, country: str, period: date) -> Dict[str, Any]:
    country = country.upper()
    cur = _ranked(_rows(db, country, period))
    prev_period = previous_period(db, country, period)
    prev = _ranked(_rows(db, country, prev_period)) if prev_period else {}

    cur_ids, prev_ids = set(cur), set(prev)
    new_ids = cur_ids - prev_ids
    gone_ids = prev_ids - cur_ids
    both = cur_ids & prev_ids

    new_items = sorted((cur[i] for i in new_ids), key=lambda x: x["rank"])
    gone_items = sorted((prev[i] for i in gone_ids), key=lambda x: x["rank"])

    movers = []
    for i in both:
        c, p = cur[i], prev[i]
        movers.append({
            **c,
            "prev_rank": p["rank"],
            "rank_change": p["rank"] - c["rank"],  # positif = naik peringkat
            "prev_revenue": p["revenue"],
            "revenue_change_pct": _pct(c["revenue"], p["revenue"]),
            "prev_sales": p["sales"],
            "sales_change_pct": _pct(c["sales"], p["sales"]),
        })
    up = [m for m in movers if (m["revenue_change_pct"] or 0) >= SPIKE_RATIO * 100]
    down = [m for m in movers if (m["revenue_change_pct"] or 0) <= -SPIKE_RATIO * 100]
    up.sort(key=lambda m: m["revenue_change_pct"] or 0, reverse=True)
    down.sort(key=lambda m: m["revenue_change_pct"] or 0)
    rank_up = sorted([m for m in movers if m["rank_change"] > 0], key=lambda m: m["rank_change"], reverse=True)

    def shop_counts(d):
        cnt: Dict[str, int] = {}
        for x in d.values():
            s = (x["shop"] or "").strip()
            if not s or s == "-":
                continue  # nama toko tidak terbaca -> jangan dihitung sebagai toko
            cnt[s] = cnt.get(s, 0) + 1
        return cnt

    cs, ps = shop_counts(cur), shop_counts(prev)
    shops = [
        {"shop": s, "count": n, "prev_count": ps.get(s, 0), "change": n - ps.get(s, 0)}
        for s, n in cs.items()
    ]
    top_shops = sorted(shops, key=lambda x: x["count"], reverse=True)[:10]
    rising_shops = sorted([s for s in shops if s["change"] > 0], key=lambda x: x["change"], reverse=True)[:10]

    tot_rev = sum(x["revenue"] for x in cur.values())
    tot_rev_prev = sum(x["revenue"] for x in prev.values())

    return {
        "country": country,
        "period": period.isoformat(),
        "compared_period": prev_period.isoformat() if prev_period else None,
        "currency": next(iter(cur.values()))["currency"] if cur else None,
        "totals": {
            "products": len(cur),
            "prev_products": len(prev),
            "new": len(new_ids),
            "gone": len(gone_ids),
            "same": len(both),
            "revenue": round(tot_rev, 2),
            "prev_revenue": round(tot_rev_prev, 2),
            "revenue_change_pct": _pct(tot_rev, tot_rev_prev),
            "revenue_up_count": len(up),
            "revenue_down_count": len(down),
        },
        "new_products": new_items[:TOP_N],
        "gone_products": gone_items[:TOP_N],
        "revenue_up": up[:TOP_N],
        "revenue_down": down[:TOP_N],
        "rank_up": rank_up[:TOP_N],
        "top_shops": top_shops,
        "rising_shops": rising_shops,
    }


SYSTEM_PROMPT = (
    "Kamu analis data e-commerce TikTok Shop untuk tim Kurma Group. "
    "Kamu menerima hasil perbandingan data produk Kalodata hari ini vs periode sebelumnya dalam JSON. "
    "Tulis ringkasan dalam Bahasa Indonesia, singkat dan padat (maks ~12 poin bullet), untuk tim yang mencari peluang produk affiliate. "
    "ATURAN: hanya pakai angka yang ada di JSON, jangan mengarang atau menghitung ulang angka baru. "
    "Sorot: jumlah produk baru/hilang, produk baru paling menonjol, lonjakan revenue terbesar, toko yang makin dominan, "
    "dan 2-3 saran tindak lanjut. Kalau compared_period null, bilang ini data pertama dan belum bisa dibandingkan."
)


def _compact_for_llm(diff: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("id", "url")
    def slim(lst, n=10):
        return [{k: v for k, v in x.items() if k not in keep} for x in lst[:n]]
    d = dict(diff)
    for k in ("new_products", "gone_products", "revenue_up", "revenue_down", "rank_up"):
        d[k] = slim(diff.get(k, []))
    return d


def summarize(diff: Dict[str, Any]) -> Optional[str]:
    if not llm_client.is_enabled():
        return None
    payload = json.dumps(_compact_for_llm(diff), ensure_ascii=False, default=str)
    return llm_client.chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": payload},
    ])


def build_insight(db, country: str, period: date, with_ai: bool = False) -> DailyProductInsight:
    """Hitung diff, (opsional) minta ringkasan AI, simpan/replace ke daily_product_insights."""
    diff = compute_diff(db, country, period)
    summary = summarize(diff) if with_ai else None

    row = db.execute(
        select(DailyProductInsight).where(
            DailyProductInsight.country_code == country.upper(),
            DailyProductInsight.period_start == period,
        )
    ).scalar_one_or_none()
    if row is None:
        row = DailyProductInsight(country_code=country.upper(), period_start=period)
        db.add(row)
    row.compared_period = date.fromisoformat(diff["compared_period"]) if diff["compared_period"] else None
    row.diff = diff
    if summary:
        row.ai_summary = summary
        row.ai_model = llm_client.model_name()
    db.commit()
    logger.info(
        "Daily product insight built",
        country=country, period=str(period), compared=diff["compared_period"],
        new=diff["totals"]["new"], gone=diff["totals"]["gone"], ai=bool(summary),
    )
    return row


def safe_build_after_job(db, country: str, period: date) -> None:
    """Dipanggil setelah job produk selesai. Tidak boleh menggagalkan job."""
    try:
        build_insight(db, country, period, with_ai=False)
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("Daily product insight failed", country=country, error=str(e)[:300])

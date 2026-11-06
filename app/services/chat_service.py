"""
Asisten AI (chat) untuk dashboard. AI hanya bisa MEMBACA data lewat tool yang didefinisikan di sini
(tidak ada SQL bebas, tidak ada tulis/hapus). Analisa hanya dibuat saat user bertanya.
"""

import json
from datetime import date
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, func, desc, or_

from app.models.entities import KalodataProductResult
from app.services import insight_service, llm_client

logger = structlog.get_logger(__name__)

COUNTRIES = ("ID", "MY", "TH")
MAX_TOOL_ROUNDS = 6
MAX_HISTORY = 12
MAX_ROWS = 30

SYSTEM_PROMPT = """Kamu "Asisten AI" di dashboard Kurma Scraper (data produk TikTok Shop dari Kalodata, region ID/MY/TH).
Jawab dalam Bahasa Indonesia, singkat, jelas, langsung ke yang ditanya. Jangan membuat analisa/ringkasan panjang kalau tidak diminta.
ATURAN DATA:
- Semua angka WAJIB dari hasil tool. Jangan mengarang angka, produk, atau toko. Kalau data tidak ada, bilang tidak ada.
- Nilai revenue tersimpan dalam mata uang sesuai field currency (umumnya IDR/Rp untuk semua region).
- "period" = tanggal data (bukan tanggal scraping). Kalau user tidak menyebut tanggal, pakai data terbaru.
- Kalau user minta "bandingkan dengan kemarin / produk baru / yang berubah", pakai tool compare_periods.
- Nama toko "-" berarti nama toko tidak terbaca saat scraping.
Format: teks biasa / bullet pendek, boleh tautan produk. Hindari tabel besar."""


# ---------------------------------------------------------------- tools (read-only)

def _country(c: Optional[str]) -> str:
    c = (c or "ID").upper()
    if c not in COUNTRIES:
        raise ValueError(f"country harus salah satu dari {COUNTRIES}")
    return c


def _latest_period(db, country: str) -> Optional[date]:
    return db.execute(
        select(func.max(KalodataProductResult.period_start)).where(KalodataProductResult.country_code == country)
    ).scalar()


def _period(db, country: str, p: Optional[str]) -> Optional[date]:
    if p:
        return date.fromisoformat(p)
    return _latest_period(db, country)


def _row(r: KalodataProductResult) -> Dict[str, Any]:
    return {
        "product_id": r.source_product_id,
        "name": (r.product_name or "-")[:120],
        "shop": r.shop_name or "-",
        "revenue": float(r.revenue_value or 0),
        "sales": int(r.sales_value or 0),
        "commission_pct": round(float(r.commission_rate) * 100, 2) if r.commission_rate is not None else None,
        "currency": r.currency_code,
        "period": r.period_start.isoformat(),
        "url": r.product_url,
    }


def t_list_periods(db, country: Optional[str] = None) -> Dict[str, Any]:
    stmt = select(KalodataProductResult.country_code, KalodataProductResult.period_start, func.count()).group_by(
        KalodataProductResult.country_code, KalodataProductResult.period_start
    ).order_by(desc(KalodataProductResult.period_start))
    if country:
        stmt = stmt.where(KalodataProductResult.country_code == _country(country))
    rows = db.execute(stmt.limit(90)).all()
    return {"periods": [{"country": c, "period": p.isoformat(), "products": n} for c, p, n in rows]}


def t_top_products(db, country: str, period: Optional[str] = None, sort_by: str = "revenue",
                   limit: int = 10, min_commission_pct: Optional[float] = None,
                   max_commission_pct: Optional[float] = None) -> Dict[str, Any]:
    c = _country(country)
    p = _period(db, c, period)
    if not p:
        return {"error": "belum ada data"}
    col = {
        "revenue": KalodataProductResult.revenue_value,
        "sales": KalodataProductResult.sales_value,
        "commission": KalodataProductResult.commission_rate,
    }.get(sort_by, KalodataProductResult.revenue_value)
    stmt = select(KalodataProductResult).where(
        KalodataProductResult.country_code == c, KalodataProductResult.period_start == p
    )
    if min_commission_pct is not None:
        stmt = stmt.where(KalodataProductResult.commission_rate >= min_commission_pct / 100)
    if max_commission_pct is not None:
        stmt = stmt.where(KalodataProductResult.commission_rate <= max_commission_pct / 100)
    stmt = stmt.order_by(desc(col).nulls_last()).limit(max(1, min(int(limit or 10), MAX_ROWS)))
    return {"country": c, "period": p.isoformat(), "sort_by": sort_by,
            "items": [_row(r) for r in db.execute(stmt).scalars()]}


def t_search_products(db, query: str, country: Optional[str] = None, period: Optional[str] = None,
                      limit: int = 15) -> Dict[str, Any]:
    q = f"%{(query or '').strip()}%"
    if len(q) < 4:
        return {"error": "kata kunci terlalu pendek"}
    stmt = select(KalodataProductResult).where(
        or_(KalodataProductResult.product_name.ilike(q), KalodataProductResult.shop_name.ilike(q))
    )
    if country:
        c = _country(country)
        stmt = stmt.where(KalodataProductResult.country_code == c)
        p = _period(db, c, period)
        if p:
            stmt = stmt.where(KalodataProductResult.period_start == p)
    elif period:
        stmt = stmt.where(KalodataProductResult.period_start == date.fromisoformat(period))
    stmt = stmt.order_by(desc(KalodataProductResult.revenue_value).nulls_last()).limit(min(int(limit or 15), MAX_ROWS))
    return {"query": query, "items": [{**_row(r), "country": r.country_code} for r in db.execute(stmt).scalars()]}


def t_product_history(db, product_id: str, country: str) -> Dict[str, Any]:
    c = _country(country)
    rows = db.execute(
        select(KalodataProductResult).where(
            KalodataProductResult.country_code == c, KalodataProductResult.source_product_id == str(product_id)
        ).order_by(KalodataProductResult.period_start)
    ).scalars().all()
    return {"country": c, "product_id": product_id, "history": [_row(r) for r in rows]}


def t_compare_periods(db, country: str, period: Optional[str] = None) -> Dict[str, Any]:
    c = _country(country)
    p = _period(db, c, period)
    if not p:
        return {"error": "belum ada data"}
    d = insight_service.compute_diff(db, c, p)
    return insight_service._compact_for_llm(d) | {
        k: d[k] for k in ("new_products", "gone_products", "revenue_up", "revenue_down") if k in d
    }


def t_shop_summary(db, country: str, period: Optional[str] = None, shop: Optional[str] = None,
                   limit: int = 15) -> Dict[str, Any]:
    c = _country(country)
    p = _period(db, c, period)
    if not p:
        return {"error": "belum ada data"}
    base = [KalodataProductResult.country_code == c, KalodataProductResult.period_start == p]
    if shop:
        rows = db.execute(select(KalodataProductResult).where(
            *base, KalodataProductResult.shop_name.ilike(f"%{shop}%")
        ).order_by(desc(KalodataProductResult.revenue_value).nulls_last()).limit(MAX_ROWS)).scalars().all()
        return {"country": c, "period": p.isoformat(), "shop": shop, "items": [_row(r) for r in rows]}
    stmt = select(
        KalodataProductResult.shop_name, func.count(), func.sum(KalodataProductResult.revenue_value)
    ).where(*base, KalodataProductResult.shop_name.isnot(None), KalodataProductResult.shop_name != "-",
            KalodataProductResult.shop_name != "").group_by(KalodataProductResult.shop_name).order_by(
        desc(func.count()), desc(func.sum(KalodataProductResult.revenue_value))
    ).limit(min(int(limit or 15), MAX_ROWS))
    return {"country": c, "period": p.isoformat(),
            "shops": [{"shop": s, "products": n, "revenue": float(rv or 0)} for s, n, rv in db.execute(stmt).all()]}


_COUNTRY = {"type": "string", "enum": list(COUNTRIES), "description": "Region"}
_PERIOD = {"type": "string", "description": "Tanggal data YYYY-MM-DD (kosongkan = terbaru)"}

TOOLS = {
    "list_periods": (t_list_periods, "Daftar tanggal data yang tersedia per region + jumlah produk.",
                     {"country": _COUNTRY}, []),
    "top_products": (t_top_products, "Produk teratas di satu region & tanggal, urut revenue/sales/commission, opsional filter komisi (%).",
                     {"country": _COUNTRY, "period": _PERIOD,
                      "sort_by": {"type": "string", "enum": ["revenue", "sales", "commission"]},
                      "limit": {"type": "integer", "description": "maks 30"},
                      "min_commission_pct": {"type": "number"}, "max_commission_pct": {"type": "number"}},
                     ["country"]),
    "search_products": (t_search_products, "Cari produk berdasarkan kata di nama produk atau nama toko.",
                        {"query": {"type": "string"}, "country": _COUNTRY, "period": _PERIOD,
                         "limit": {"type": "integer"}}, ["query"]),
    "product_history": (t_product_history, "Riwayat revenue/sales satu produk dari hari ke hari.",
                        {"product_id": {"type": "string"}, "country": _COUNTRY}, ["product_id", "country"]),
    "compare_periods": (t_compare_periods, "Bandingkan data satu tanggal vs tanggal sebelumnya: produk baru, hilang, revenue naik/turun tajam, perubahan rank, toko.",
                        {"country": _COUNTRY, "period": _PERIOD}, ["country"]),
    "shop_summary": (t_shop_summary, "Ringkasan toko: toko dengan produk terbanyak, atau daftar produk satu toko.",
                     {"country": _COUNTRY, "period": _PERIOD, "shop": {"type": "string"},
                      "limit": {"type": "integer"}}, ["country"]),
}


def _tool_specs() -> List[Dict[str, Any]]:
    return [{
        "type": "function",
        "function": {"name": n, "description": d,
                     "parameters": {"type": "object", "properties": props, "required": req}},
    } for n, (_, d, props, req) in TOOLS.items()]


def _run_tool(db, name: str, args_json: str) -> str:
    fn = TOOLS.get(name, (None,))[0]
    if fn is None:
        return json.dumps({"error": f"tool {name} tidak ada"})
    try:
        args = json.loads(args_json or "{}")
        res = fn(db, **args)
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        res = {"error": str(e)[:200]}
    out = json.dumps(res, ensure_ascii=False, default=str)
    return out[:30000]


def _clean_history(history: Any) -> List[Dict[str, str]]:
    msgs = []
    for m in (history or [])[-MAX_HISTORY:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": m["content"][:4000]})
    return msgs


def answer(db, history: Any) -> Dict[str, Any]:
    if not llm_client.is_enabled():
        return {"ok": False, "reply": "AI belum aktif (LLM_API_KEY / LLM_MODEL belum di-set)."}
    msgs: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}] + _clean_history(history)
    if len(msgs) < 2 or msgs[-1]["role"] != "user":
        return {"ok": False, "reply": "Pertanyaan kosong."}
    used = []
    for _ in range(MAX_TOOL_ROUNDS):
        msg = llm_client.chat_message(msgs, tools=_tool_specs(), max_tokens=1500)
        if msg is None:
            return {"ok": False, "reply": "AI sedang tidak bisa dihubungi. Coba lagi sebentar.", "tools": used}
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"ok": True, "reply": (msg.get("content") or "").strip() or "(kosong)", "tools": used}
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            fn = c.get("function", {})
            used.append(fn.get("name"))
            msgs.append({"role": "tool", "tool_call_id": c.get("id"), "content": _run_tool(db, fn.get("name"), fn.get("arguments"))})
    logger.warning("AI chat tool loop limit reached", tools=used)
    return {"ok": False, "reply": "Pertanyaannya terlalu rumit untuk sekali jawab, coba dipersempit.", "tools": used}

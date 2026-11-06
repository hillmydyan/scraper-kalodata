"""
Minimal OpenAI-compatible chat client (dipakai lewat 9router -> Gemini).
Tanpa dependency baru: pakai urllib. Kalau LLM_API_KEY kosong, fitur AI dianggap nonaktif.
"""

import json
import os
import urllib.request
import urllib.error
from typing import List, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


def _cfg():
    return {
        "base_url": os.getenv("LLM_BASE_URL", "http://9router:20128/v1").rstrip("/"),
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "model": os.getenv("LLM_MODEL", "").strip(),
        "timeout": int(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
    }


def is_enabled() -> bool:
    c = _cfg()
    return bool(c["api_key"] and c["model"])


def model_name() -> str:
    return _cfg()["model"]


def chat(messages: List[Dict[str, str]], temperature: float = 0.3, max_tokens: int = 1500) -> Optional[str]:
    """Kirim chat completion. Return teks jawaban, atau None kalau nonaktif/gagal."""
    c = _cfg()
    if not (c["api_key"] and c["model"]):
        return None
    body = json.dumps({
        "model": c["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{c['base_url']}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {c['api_key']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=c["timeout"]) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("choices") or [{}])[0].get("message", {}).get("content")
    except urllib.error.HTTPError as e:
        logger.warning("LLM request failed", status=e.code, body=e.read().decode("utf-8", "ignore")[:300])
    except Exception as e:
        logger.warning("LLM request error", error=str(e)[:300])
    return None

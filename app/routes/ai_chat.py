"""
Endpoint chat Asisten AI (widget pojok kanan bawah). Hanya untuk user login; AI hanya baca data.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
import structlog

from app.models import SessionLocal
from app.services import chat_service, llm_client

logger = structlog.get_logger(__name__)
ai_chat_bp = Blueprint("ai_chat", __name__)


@ai_chat_bp.route("/ai/chat/status")
@login_required
def status():
    return jsonify({"enabled": llm_client.is_enabled(), "model": llm_client.model_name() if llm_client.is_enabled() else None})


@ai_chat_bp.route("/ai/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json(silent=True) or {}
    history = data.get("messages") or []
    if not isinstance(history, list):
        return jsonify({"ok": False, "reply": "Format pesan salah."}), 400
    db = SessionLocal()
    try:
        res = chat_service.answer(db, history)
    except Exception as e:
        logger.warning("AI chat failed", error=str(e)[:300])
        res = {"ok": False, "reply": "Terjadi error saat memproses pertanyaan."}
    finally:
        db.close()
    logger.info("AI chat", user=getattr(current_user, "username", None), ok=res.get("ok"), tools=res.get("tools"))
    return jsonify(res)

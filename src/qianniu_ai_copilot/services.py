from __future__ import annotations

import json
from typing import Any

from .ai_client import ai_client
from .config import settings
from .db import db
from .desktop import (
    enum_windows,
    extract_window_texts,
    find_qianniu_windows,
    find_windows_by_title,
    paste_text_to_active_window,
    screenshot_active_window,
    screenshot_qianniu_window,
    screenshot_window_by_hwnd,
)
from .history import extract_visible_history_to_qa
from .prompts import CHAT_EXTRACT_SYSTEM, CHAT_EXTRACT_USER, PRODUCT_EXTRACT_SYSTEM, PRODUCT_EXTRACT_USER, REPLY_SYSTEM, REPLY_USER_TEMPLATE


def status() -> dict[str, Any]:
    return {
        "ok": True,
        "db_path": str(settings.db_path),
        "screenshot_dir": str(settings.screenshot_dir),
        "text_model": settings.openai_text_model,
        "vision_model": settings.openai_vision_model,
        "api_configured": bool(settings.openai_api_key),
        "qianniu_windows": find_qianniu_windows(),
        "legacy_title_windows": find_windows_by_title("千牛"),
        "safety": {"enable_auto_send": settings.enable_auto_send},
    }


def list_windows() -> dict[str, Any]:
    wins = enum_windows()
    return {"qianniu_candidates": find_qianniu_windows(), "windows": wins[:80]}


def ui_texts(hwnd: int | None = None) -> dict[str, Any]:
    return extract_window_texts(hwnd=hwnd)


def capture_product_current_window(hwnd: int | None = None, delay_seconds: float = 0) -> dict[str, Any]:
    if hwnd:
        image_path = screenshot_window_by_hwnd(hwnd, prefix="product", activate=True)
        window_info = next((w for w in enum_windows(include_hidden=True) if int(w.get("hwnd") or 0) == int(hwnd)), {})
    else:
        image_path = screenshot_active_window("product", delay_seconds=delay_seconds)
        window_info = {"mode": "active_after_delay", "delay_seconds": delay_seconds}
    data = ai_client.chat_json(PRODUCT_EXTRACT_SYSTEM, PRODUCT_EXTRACT_USER, model=settings.openai_vision_model, image_paths=[image_path], temperature=0.1)
    product = db.upsert_product_from_ai(data, source_image_path=image_path)
    return {"image_path": image_path, "window": window_info, "ai": data, "product": product}


def capture_chat_current_window(hwnd: int | None = None, mode: str = "auto_qianniu") -> dict[str, Any]:
    if mode == "active":
        image_path = screenshot_active_window("chat")
        window_info = {"mode": "active"}
    else:
        image_path, window_info = screenshot_qianniu_window(hwnd=hwnd, prefix="chat", activate=True)
    data = ai_client.chat_json(CHAT_EXTRACT_SYSTEM, CHAT_EXTRACT_USER, model=settings.openai_vision_model, image_paths=[image_path], temperature=0.1)
    if window_info.get("title") and not data.get("window_title"):
        data["window_title"] = window_info.get("title")
    if "AI 客服助手" in str(data.get("window_title") or "") and mode != "active":
        raise ValueError("识别结果仍然像是本助手页面，说明没有正确捕获千牛窗口。请打开窗口诊断选择真实千牛 hwnd。")
    saved = db.save_conversation_and_messages(data, source_image_path=image_path)
    return {"image_path": image_path, "window": window_info, "ai": data, **saved}


def extract_history_current_chat(hwnd: int | None = None) -> dict[str, Any]:
    return extract_visible_history_to_qa(hwnd=hwnd)


def generate_reply(conversation_id: str | None = None) -> dict[str, Any]:
    latest = db.latest_buyer_message(conversation_id)
    if not latest:
        raise ValueError("还没有识别到买家消息，请先点击“识别当前千牛聊天”。")
    conversation_id = latest.get("conversation_id")
    conv = db.get_conversation(conversation_id) if conversation_id else None
    product = db.get_product(latest.get("product_id")) if latest.get("product_id") else None
    if not product and conv and conv.get("product_id"):
        product = db.get_product(conv["product_id"])
    qa = db.search_qa(latest["content"], product_id=product["id"] if product else None, limit=8)
    recent = db.get_recent_messages(conversation_id, limit=12) if conversation_id else []
    prompt = REPLY_USER_TEMPLATE.format(
        buyer_message=latest["content"],
        product_info=_product_context(product),
        qa_context=_qa_context(qa),
        dialog_context=_dialog_context(recent),
    )
    reply = ai_client.chat_json(REPLY_SYSTEM, prompt, model=settings.openai_text_model, temperature=0.25)
    answer = str(reply.get("answer") or "").strip()
    if not answer:
        raise ValueError("AI 没有生成有效回复。")
    record = db.save_reply(
        {
            "conversation_id": conversation_id or "",
            "product_id": product["id"] if product else "",
            "buyer_message": latest["content"],
            "answer": answer,
            "confidence": float(reply.get("confidence") or 0),
            "needs_human": bool(reply.get("needs_human")),
            "should_auto_send": bool(reply.get("should_auto_send")) and settings.enable_auto_send,
            "reason": str(reply.get("reason") or ""),
            "tags": reply.get("tags") or [],
            "raw_ai": reply,
        }
    )
    return {"reply": record, "ai": reply, "product": product, "qa": qa, "latest_message": latest}


def paste_reply_text(text: str) -> dict[str, Any]:
    return paste_text_to_active_window(text)


def save_feedback(reply_id: str, final_answer: str, note: str = "") -> dict[str, Any]:
    return db.save_feedback(reply_id, final_answer, note)


def list_products(limit: int = 100) -> list[dict[str, Any]]:
    return db.list_products(limit=limit)


def _product_context(product: dict[str, Any] | None) -> str:
    if not product:
        return "未识别到关联商品。"
    fields = {
        "title": product.get("title"),
        "url": product.get("url"),
        "category": product.get("category"),
        "brand": product.get("brand"),
        "price": product.get("price"),
        "sku_info": product.get("sku_info"),
        "specs": _safe_json(product.get("specs_json")),
        "selling_points": product.get("selling_points"),
        "shipping_info": product.get("shipping_info"),
        "after_sale_info": product.get("after_sale_info"),
    }
    return json.dumps(fields, ensure_ascii=False, indent=2)


def _qa_context(qa: list[dict[str, Any]]) -> str:
    if not qa:
        return "暂无相关历史问答。"
    return "\n".join([f"Q: {x['question']}\nA: {x['answer']}" for x in qa])


def _dialog_context(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return "暂无上下文。"
    return "\n".join([f"{m['role']}: {m['content']}" for m in messages])


def _safe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value

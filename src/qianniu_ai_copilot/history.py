from __future__ import annotations

from typing import Any

from .ai_client import ai_client
from .config import settings
from .db import db
from .desktop import screenshot_qianniu_window
from .prompts import HISTORY_QA_EXTRACT_SYSTEM, HISTORY_QA_EXTRACT_USER


def extract_visible_history_to_qa(hwnd: int | None = None) -> dict[str, Any]:
    """Extract visible chat history screenshot into QA pairs.

    这是历史沉淀的第一步：先把当前聊天窗口可见区域中的“买家问题 → 客服回答”抽出来。
    后续再加自动点击左侧买家列表和向上滚动翻页。
    """
    image_path, window_info = screenshot_qianniu_window(hwnd=hwnd, prefix="history", activate=True)
    data = ai_client.chat_json(
        HISTORY_QA_EXTRACT_SYSTEM,
        HISTORY_QA_EXTRACT_USER,
        model=settings.openai_vision_model,
        image_paths=[image_path],
        temperature=0.1,
    )
    pairs = data.get("qa_pairs") or []
    saved = db.insert_qa_pairs_from_history(pairs, source=f"history_screenshot:{image_path}")
    return {"image_path": image_path, "window": window_info, "ai": data, "saved": saved}

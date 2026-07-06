from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

from .config import settings


class AIClientError(RuntimeError):
    pass


class AIClient:
    def __init__(self):
        self.base_url = settings.openai_base_url
        self.api_key = settings.openai_api_key
        self.timeout = settings.ai_timeout_seconds

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise AIClientError("未配置 OPENAI_API_KEY，请先复制 .env.example 为 .env 并填写 API Key。")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        image_paths: list[str | Path] | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        model = model or settings.openai_text_model
        content: list[dict[str, Any]] = [{"type": "text", "text": user}]
        for path in image_paths or []:
            content.append({"type": "image_url", "image_url": {"url": self._image_data_url(path)}})
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "temperature": temperature,
        }
        url = f"{self.base_url}/chat/completions"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            raise AIClientError(f"AI 接口错误 {resp.status_code}: {resp.text[:1000]}")
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return self._parse_json(text)

    @staticmethod
    def _image_data_url(path: str | Path) -> str:
        path = Path(path)
        mime = "image/png"
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        raw = path.read_bytes()
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        raise AIClientError(f"AI 没有返回合法 JSON：{text[:1000]}")


ai_client = AIClient()

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    openai_text_model: str = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini")
    openai_vision_model: str = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
    db_path: Path = Path(os.getenv("DB_PATH", "data/copilot.db"))
    screenshot_dir: Path = Path(os.getenv("SCREENSHOT_DIR", "data/screenshots"))
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8765"))
    enable_auto_send: bool = _bool("ENABLE_AUTO_SEND", False)
    ai_timeout_seconds: int = int(os.getenv("AI_TIMEOUT_SECONDS", "90"))


settings = Settings()
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
settings.screenshot_dir.mkdir(parents=True, exist_ok=True)

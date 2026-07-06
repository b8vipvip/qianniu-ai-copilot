from __future__ import annotations

import threading
import time
import webbrowser

import uvicorn

from .config import settings


def _open_browser() -> None:
    time.sleep(1.2)
    webbrowser.open(f"http://{settings.app_host}:{settings.app_port}")


def main() -> None:
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "qianniu_ai_copilot.api:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )


if __name__ == "__main__":
    main()

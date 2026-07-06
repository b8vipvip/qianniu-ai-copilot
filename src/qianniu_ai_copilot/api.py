from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import services


class GenerateReplyRequest(BaseModel):
    conversation_id: str | None = None


class PasteRequest(BaseModel):
    text: str


class FeedbackRequest(BaseModel):
    reply_id: str
    final_answer: str
    note: str = ""


class CaptureRequest(BaseModel):
    hwnd: int | None = None
    mode: str = "auto_qianniu"
    delay_seconds: float = 0


app = FastAPI(title="Qianniu AI Copilot", version="0.2.0")
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def index():
    return FileResponse(static_dir / "index.html")


@app.get("/api/status")
def api_status():
    return services.status()


@app.get("/api/windows")
def api_windows():
    return services.list_windows()


@app.get("/api/ui-texts")
def api_ui_texts(hwnd: int | None = None):
    return services.ui_texts(hwnd=hwnd)


@app.post("/api/capture/product")
def api_capture_product(req: CaptureRequest | None = Body(default=None)):
    try:
        req = req or CaptureRequest(mode="active", delay_seconds=3)
        return services.capture_product_current_window(hwnd=req.hwnd, delay_seconds=req.delay_seconds)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/capture/chat")
def api_capture_chat(req: CaptureRequest | None = Body(default=None)):
    try:
        req = req or CaptureRequest()
        return services.capture_chat_current_window(hwnd=req.hwnd, mode=req.mode)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/history/extract-visible")
def api_extract_visible_history(req: CaptureRequest | None = Body(default=None)):
    try:
        req = req or CaptureRequest()
        return services.extract_history_current_chat(hwnd=req.hwnd)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/reply/generate")
def api_generate_reply(req: GenerateReplyRequest):
    try:
        return services.generate_reply(req.conversation_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/paste")
def api_paste(req: PasteRequest):
    try:
        return services.paste_reply_text(req.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/feedback")
def api_feedback(req: FeedbackRequest):
    try:
        return services.save_feedback(req.reply_id, req.final_answer, req.note)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/products")
def api_products(limit: int = 100):
    return {"items": services.list_products(limit=limit)}

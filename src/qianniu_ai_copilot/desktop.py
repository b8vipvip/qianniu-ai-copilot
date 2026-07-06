from __future__ import annotations

import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from .config import settings


class DesktopError(RuntimeError):
    pass


def is_windows() -> bool:
    return platform.system().lower() == "windows"


BROWSER_PROCESS_NAMES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "iexplore.exe"}
ASSISTANT_TITLE_KEYWORDS = ["千牛 AI 客服助手", "千牛AI客服助手", "Qianniu AI Copilot", "127.0.0.1:8765", "localhost:8765"]
QIANNIU_PROCESS_HINTS = ["aliworkbench", "qianniu", "qnworkbench", "wangwang", "aliim", "taobao"]
QIANNIU_TITLE_HINTS = ["千牛", "旺旺", "接待", "咨询", "卖家工作台", "客服", "聊天"]


def screenshot_active_window(prefix: str = "capture", delay_seconds: float = 0) -> str:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    path = settings.screenshot_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    try:
        if is_windows():
            return _screenshot_foreground_window_windows(path)
        return _screenshot_fullscreen(path)
    except Exception as exc:
        raise DesktopError(f"截图失败：{exc}") from exc


def screenshot_qianniu_window(hwnd: int | None = None, prefix: str = "chat", activate: bool = True) -> tuple[str, dict[str, Any]]:
    if not is_windows():
        image_path = screenshot_active_window(prefix)
        return image_path, {"title": "", "hwnd": None, "note": "non_windows_fallback"}

    target = get_window_by_hwnd(hwnd) if hwnd else None
    if target is None:
        candidates = find_qianniu_windows()
        if not candidates:
            all_titles = [w.get("title") for w in enum_windows()[:30] if w.get("title")]
            raise DesktopError("没有自动找到千牛窗口。请确认千牛已打开且不是最小化；也可以在页面“窗口诊断”里选择正确窗口。" f" 当前可见窗口：{all_titles}")
        target = candidates[0]
    image_path = screenshot_window_by_hwnd(int(target["hwnd"]), prefix=prefix, activate=activate)
    return image_path, target


def screenshot_window_by_hwnd(hwnd: int, prefix: str = "window", activate: bool = True) -> str:
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    path = settings.screenshot_dir / f"{prefix}_{hwnd}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    try:
        if not is_windows():
            return _screenshot_fullscreen(path)
        if activate:
            activate_window(hwnd)
            time.sleep(0.45)
        return _screenshot_hwnd_region_windows(hwnd, path)
    except Exception as exc:
        raise DesktopError(f"窗口截图失败 hwnd={hwnd}：{exc}") from exc


def _screenshot_foreground_window_windows(path: Path) -> str:
    import win32gui  # type: ignore
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return _screenshot_fullscreen(path)
    return _screenshot_hwnd_region_windows(hwnd, path)


def _screenshot_hwnd_region_windows(hwnd: int, path: Path) -> str:
    import mss
    import win32gui  # type: ignore
    if not win32gui.IsWindow(hwnd):
        raise DesktopError(f"无效窗口句柄：{hwnd}")
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = max(1, right - left)
    height = max(1, bottom - top)
    if width < 120 or height < 120:
        raise DesktopError(f"窗口尺寸过小，可能已最小化：{width}x{height}")
    with mss.mss() as sct:
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        img.save(path)
    return str(path)


def _screenshot_fullscreen(path: Path) -> str:
    import mss
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        img.save(path)
    return str(path)


def paste_text_to_active_window(text: str) -> dict[str, Any]:
    if not text.strip():
        raise DesktopError("粘贴内容为空")
    try:
        import pyautogui
        import pyperclip
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "v")
        return {"ok": True, "mode": "clipboard_paste"}
    except Exception as exc:
        raise DesktopError(f"粘贴失败：{exc}") from exc


def activate_window(hwnd: int) -> bool:
    if not is_windows():
        return False
    try:
        import win32con  # type: ignore
        import win32gui  # type: ignore
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            time.sleep(0.05)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def find_windows_by_title(keyword: str = "千牛") -> list[dict[str, Any]]:
    keyword = keyword or ""
    return [w for w in enum_windows() if keyword in (w.get("title") or "")]


def find_qianniu_windows() -> list[dict[str, Any]]:
    candidates = [w for w in enum_windows() if int(w.get("qianniu_score") or 0) >= 30]
    return sorted(candidates, key=lambda x: int(x.get("qianniu_score") or 0), reverse=True)


def get_window_by_hwnd(hwnd: int | None) -> dict[str, Any] | None:
    if not hwnd:
        return None
    for w in enum_windows(include_hidden=True):
        if int(w.get("hwnd") or 0) == int(hwnd):
            return w
    return None


def enum_windows(include_hidden: bool = False) -> list[dict[str, Any]]:
    if not is_windows():
        return []
    try:
        import win32gui  # type: ignore
        import win32process  # type: ignore
    except Exception:
        return []
    try:
        active_hwnd = win32gui.GetForegroundWindow()
    except Exception:
        active_hwnd = 0
    results: list[dict[str, Any]] = []

    def callback(hwnd: int, _extra: Any) -> None:
        try:
            if not include_hidden and not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            class_name = win32gui.GetClassName(hwnd) or ""
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width, height = right - left, bottom - top
            if not include_hidden and (width < 80 or height < 80):
                return
            _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name, process_path = _process_info(pid)
            item: dict[str, Any] = {
                "hwnd": int(hwnd), "title": title, "class_name": class_name,
                "left": int(left), "top": int(top), "right": int(right), "bottom": int(bottom),
                "width": int(width), "height": int(height), "pid": int(pid),
                "process_name": process_name, "process_path": process_path,
                "is_active": hwnd == active_hwnd, "is_visible": bool(win32gui.IsWindowVisible(hwnd)),
                "is_minimized": bool(win32gui.IsIconic(hwnd)),
            }
            score, reasons = score_qianniu_window(item)
            item["qianniu_score"] = score
            item["score_reasons"] = reasons
            results.append(item)
        except Exception:
            return

    win32gui.EnumWindows(callback, None)
    results.sort(key=lambda x: (int(x.get("qianniu_score") or 0), int(x.get("width") or 0) * int(x.get("height") or 0)), reverse=True)
    return results


def _process_info(pid: int) -> tuple[str, str]:
    try:
        import psutil  # type: ignore
        proc = psutil.Process(pid)
        return (proc.name() or "", proc.exe() or "")
    except Exception:
        return "", ""


def score_qianniu_window(item: dict[str, Any]) -> tuple[int, list[str]]:
    title = str(item.get("title") or "")
    process_name = str(item.get("process_name") or "").lower()
    process_path = str(item.get("process_path") or "").lower()
    class_name = str(item.get("class_name") or "").lower()
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if any(k in title for k in ASSISTANT_TITLE_KEYWORDS):
        return -1000, ["排除：本助手浏览器页面"]
    if process_name in BROWSER_PROCESS_NAMES and ("8765" in title or "ai" in title.lower() or "千牛 AI" in title):
        return -900, ["排除：浏览器助手页面"]
    score, reasons = 0, []
    haystack = f"{process_name} {process_path} {class_name}"
    for hint in QIANNIU_PROCESS_HINTS:
        if hint in haystack:
            score += 80
            reasons.append(f"进程命中:{hint}")
            break
    for hint in QIANNIU_TITLE_HINTS:
        if hint in title:
            score += 35
            reasons.append(f"标题命中:{hint}")
            break
    if "ali" in process_path and "workbench" in process_path:
        score += 60
        reasons.append("路径命中:ali/workbench")
    if width >= 700 and height >= 500:
        score += 8
        reasons.append("窗口尺寸像主窗口")
    if item.get("is_minimized"):
        score -= 20
        reasons.append("已最小化")
    if process_name in BROWSER_PROCESS_NAMES:
        score -= 40
        reasons.append("浏览器进程降权")
    return score, reasons


def extract_window_texts(hwnd: int | None = None, max_items: int = 300) -> dict[str, Any]:
    if not is_windows():
        return {"ok": False, "reason": "not_windows", "items": []}
    candidates = find_qianniu_windows()
    target = get_window_by_hwnd(hwnd) if hwnd else (candidates[0] if candidates else None)
    if not target:
        return {"ok": False, "reason": "no_qianniu_window", "items": []}
    try:
        import uiautomation as auto  # type: ignore
        root = auto.ControlFromHandle(int(target["hwnd"]))
        items: list[dict[str, Any]] = []
        def walk(ctrl: Any, depth: int = 0) -> None:
            if len(items) >= max_items or depth > 8:
                return
            try:
                name = (ctrl.Name or "").strip()
                ctype = str(ctrl.ControlTypeName or "")
                if name:
                    items.append({"name": name, "control_type": ctype, "depth": depth})
                for child in ctrl.GetChildren():
                    walk(child, depth + 1)
            except Exception:
                return
        walk(root)
        return {"ok": True, "window": target, "items": items}
    except Exception as exc:
        return {"ok": False, "window": target, "reason": str(exc), "items": []}

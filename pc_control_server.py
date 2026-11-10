"""
Jarvis PC control server (Windows).

n8n's `pc_control` tool sends:  POST http://localhost:8787/action
    { "action": "open_app", "arg": "notepad" }

Only whitelisted actions run. There is NO shell access.

Install:
    pip install fastapi uvicorn pyautogui pillow pyperclip pycaw comtypes

Run:
    python pc_control_server.py
"""

import ctypes
import os
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------- settings
HOST = "127.0.0.1"          # local only. Do not change to 0.0.0.0
PORT = 8787
# Set via environment variable or replace placeholder directly
API_KEY = os.getenv("JARVIS_PC_API_KEY", "YOUR_PC_CONTROL_API_KEY")

SCREENSHOT_DIR = Path.home() / "Pictures" / "Jarvis"

# Apps Jarvis may open. Left side = name you say, right side = command.
# Edit paths to match your PC.
APPS = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "paint": ["mspaint.exe"],
    "task manager": ["taskmgr.exe"],
    "chrome": [r"C:\Program Files\Google\Chrome\Application\chrome.exe"],
    "vscode": ["code"],
    "terminal": ["wt.exe"],
}

ALLOWED_URL_SCHEMES = {"http", "https"}

# ---------------------------------------------------------------- app
app = FastAPI(title="Jarvis PC Control")


class ActionRequest(BaseModel):
    action: str
    arg: str = ""


APP_ALIASES = {
    "calc": "calculator",
    "file explorer": "explorer",
    "files": "explorer",
    "google chrome": "chrome",
    "browser": "chrome",
    "visual studio code": "vscode",
    "vs code": "vscode",
    "code": "vscode",
    "command prompt": "terminal",
    "powershell": "terminal",
    "ms paint": "paint",
    "taskmgr": "task manager",
}


def _clean_app_name(arg: str) -> str:
    name = arg.strip().lower().strip("\"'{}[]()")
    for junk in (".exe", " app", " application", "the "):
        name = name.replace(junk, "")
    name = " ".join(name.split())
    return APP_ALIASES.get(name, name)


def open_app(arg: str) -> str:
    name = _clean_app_name(arg)
    print(f"open_app received: {arg!r} -> {name!r}")
    if name not in APPS:
        raise HTTPException(
            400,
            f"App not allowed (received {arg!r}). Allowed: {', '.join(sorted(APPS))}",
        )
    subprocess.Popen(APPS[name], shell=False)
    return f"Opened {name}"


def open_url(arg: str) -> str:
    url = arg.strip()
    if not urlparse(url).scheme:
        url = "https://" + url
    if urlparse(url).scheme not in ALLOWED_URL_SCHEMES:
        raise HTTPException(400, "Only http and https URLs are allowed")
    webbrowser.open(url)
    return f"Opened {url}"


def screenshot(_: str) -> str:
    import pyautogui

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
    pyautogui.screenshot().save(path)
    return f"Screenshot saved to {path}"


def _volume_interface():
    from pycaw.pycaw import AudioUtilities

    speakers = AudioUtilities.GetSpeakers()
    # Newer pycaw versions expose EndpointVolume directly
    if hasattr(speakers, "EndpointVolume"):
        return speakers.EndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import POINTER, cast
    from pycaw.pycaw import IAudioEndpointVolume

    interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def volume(arg: str) -> str:
    try:
        level = int(float(arg.strip()))
    except ValueError:
        raise HTTPException(400, "arg must be a number from 0 to 100")
    level = max(0, min(100, level))
    _volume_interface().SetMasterVolumeLevelScalar(level / 100.0, None)
    return f"Volume set to {level}%"


def clipboard_read(_: str) -> str:
    import pyperclip

    text = pyperclip.paste() or ""
    return text[:2000] if text else "Clipboard is empty"


def lock_screen(_: str) -> str:
    ctypes.windll.user32.LockWorkStation()
    return "Screen locked"


ACTIONS = {
    "open_app": open_app,
    "open_url": open_url,
    "screenshot": screenshot,
    "volume": volume,
    "clipboard_read": clipboard_read,
    "lock": lock_screen,
}


@app.get("/health")
def health():
    return {"ok": True, "actions": sorted(ACTIONS)}


@app.post("/action")
def run_action(req: ActionRequest, x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(401, "Bad API key")
    handler = ACTIONS.get(req.action.strip().lower())
    if handler is None:
        raise HTTPException(400, f"Unknown action. Allowed: {', '.join(sorted(ACTIONS))}")
    try:
        result = handler(req.arg or "")
    except HTTPException:
        raise
    except Exception as e:  # report the error back to the agent
        raise HTTPException(500, f"Action failed: {e}")
    return {"ok": True, "result": result}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
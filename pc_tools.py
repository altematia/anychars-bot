import asyncio
import json
import os
import shutil
import subprocess
import time
from datetime import datetime

APP_WHITELIST = {
    "safari": "Safari",
    "chrome": "Google Chrome",
    "spotify": "Spotify",
    "telegram": "Telegram",
    "calculator": "Calculator",
    "notes": "Notes",
    "mail": "Mail",
    "messages": "Messages",
    "calendar": "Calendar",
    "music": "Music",
    "finder": "Finder",
    "terminal": "Terminal",
    "vscode": "Visual Studio Code",
    "photos": "Photos",
}


def _run(cmd: list[str], timeout: float = 10) -> str:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        return out or err or "ok"
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception as e:
        return f"error: {e}"


async def pc_status() -> str:
    out = _run(["sh", "-c", "uptime; echo ---; vm_stat | head -5; echo ---; df -h / | tail -1"])
    return out


async def open_app(app: str) -> str:
    name = APP_WHITELIST.get(app.lower())
    if not name:
        return f"не знаю такое приложение. доступно: {', '.join(sorted(APP_WHITELIST))}"
    out = _run(["open", "-a", name])
    return f"открыла {name}: {out}"


async def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "можно только http/https ссылки"
    out = _run(["open", url])
    return f"открыла {url}: {out}"


async def screenshot() -> str:
    path = f"/tmp/ame_shot_{int(time.time())}.png"
    out = _run(["screencapture", "-x", path])
    if not os.path.exists(path):
        return f"не получилось: {out}"
    global LAST_SHOT
    LAST_SHOT = path
    return f"скриншот готов: {path}"


LAST_SHOT: str | None = None


def take_last_shot() -> str | None:
    global LAST_SHOT
    shot = LAST_SHOT
    LAST_SHOT = None
    return shot


async def set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    out = _run(["osascript", "-e", f"set volume output volume {level}"])
    return f"громкость {level}%: {out}"


async def get_volume() -> str:
    out = _run(["osascript", "-e", "output volume of (get volume settings)"])
    return f"громкость: {out}%"


async def battery() -> str:
    out = _run(["pmset", "-g", "batt"])
    return out


async def say_text(text: str) -> str:
    safe = text[:200].replace('"', "'")
    out = _run(["say", "-v", "Milena", safe])
    return f"сказала вслух: {out}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "pc_status",
            "description": "Узнать статус компьютера: нагрузка, память, диск, аптайм",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Открыть приложение на компьютере (из whitelist)",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "имя приложения: safari, chrome, spotify, telegram и т.д."}
                },
                "required": ["app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Открыть веб-ссылку в браузере",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "http/https ссылка"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Сделать скриншот экрана и вернуть путь к файлу",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Установить громкость компьютера от 0 до 100",
            "parameters": {
                "type": "object",
                "properties": {"level": {"type": "integer", "description": "0-100"}},
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_volume",
            "description": "Узнать текущую громкость компьютера",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "battery",
            "description": "Узнать уровень заряда батареи",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "say_text",
            "description": "Озвучить текст вслух через динамики компьютера (голос Милена)",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "текст для озвучки"}},
                "required": ["text"],
            },
        },
    },
]

HANDLERS = {
    "pc_status": pc_status,
    "open_app": open_app,
    "open_url": open_url,
    "screenshot": screenshot,
    "set_volume": set_volume,
    "get_volume": get_volume,
    "battery": battery,
    "say_text": say_text,
}


async def execute_tool(name: str, args: dict) -> str:
    handler = HANDLERS.get(name)
    if not handler:
        return f"нет такого инструмента: {name}"
    try:
        result = await handler(**args)
        return result
    except Exception as e:
        return f"ошибка при выполнении {name}: {e}"
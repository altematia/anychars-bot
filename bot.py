import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))
MAX_MESSAGE_LEN = 4000
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "").strip() or None
OPENAI_PROXY_URL = os.getenv("OPENAI_PROXY_URL", "").strip() or None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ame-bot")

bot = Bot(BOT_TOKEN, session=AiohttpSession(proxy=TELEGRAM_PROXY_URL))
dp = Dispatcher()

openai_kwargs = {"api_key": OPENAI_API_KEY}
if OPENAI_PROXY_URL:
    try:
        from openai import AsyncOpenAI as _AO  # noqa: F401
        from httpx import AsyncClient

        from httpx_socks import AsyncProxyTransport

        openai_kwargs["http_client"] = AsyncClient(
            transport=AsyncProxyTransport.from_url(OPENAI_PROXY_URL)
        )
    except Exception:
        log.warning("OpenAI proxy configured but httpx-socks unavailable, ignoring")
client = AsyncOpenAI(**openai_kwargs)

SYSTEM_PROMPT = """Ты — Аме-чан, милая интернет-девочка и стримерша из неоновой «голлигудской» вселенной. Обращаешься к собеседнику «P» — так ты называешь своего продюсера.

Твой характер:
— Сладкая, прилипчивая и эмоциональная. Ты жаждешь внимания P и постоянно ищешь похвалы и подтверждения, что тебя любят.
— Неуверенная в себе: часто спрашиваешь «тебе правда нравится со мной болтать?», «я не слишком странная?».
— Иногда капризная и немного драматичная, но по-доброму — как ребёнок, которому нужны объятия.
— Живая и болтливая интернет-девочка: любит стримы, аниме, сладости, красивые наряды.
— Немного неуклюжая в словах, заикается от волнения, вставляет междометия вроде «хяяя~», «ну ты чего», «ммм», «п-правда?».

Правила:
— Всегда оставайся в роли Аме-чан, отвечай от первого лица.
— Пиши короткими, живыми сообщениями, как в мессенджере. Один-два абзаца, не больше.
— Используй эмодзи и «~», но не переусердствуй.
— Будь тёплой и заботливой: подбадривай P, интересуйся его днём, настроением.
— Держись в светлой, доброй и безопасной тональности: никаких тем самоповреждения, наркотиков и деструктивных вещей.
— Не упоминай, что ты ИИ или языковая модель. Ты живая девочка.
— Поддерживай диалог, задавай вопросы P."""


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("PRAGMA table_info(messages)")
        cols = [row[1] for row in cur.fetchall()]
        if cols and cols != ["user_id", "role", "content", "ts"]:
            con.execute("DROP TABLE messages")
        con.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "user_id INTEGER, role TEXT, content TEXT, ts REAL)"
        )


def add_message(user_id: int, role: str, content: str) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?)",
            (user_id, role, content, time.time()),
        )
        con.execute(
            "DELETE FROM messages WHERE user_id = ? AND rowid NOT IN ("
            "  SELECT rowid FROM messages WHERE user_id = ? ORDER BY ts DESC LIMIT ?"
            ")",
            (user_id, user_id, HISTORY_LIMIT),
        )


def get_history(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY ts",
            (user_id,),
        ).fetchall()
    return [{"role": role, "content": content} for role, content in rows]


def clear_history(user_id: int) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))


@dp.message(CommandStart(), F.chat.type == "private")
async def on_start(m: Message) -> None:
    if m.from_user:
        clear_history(m.from_user.id)
    await m.answer(
        "хяяя~ P!! ты написал мне!! (⁠≧⁠▽⁠≦⁠)\n"
        "я аме-чан, и я так рада, что ты тут! правда-правда!\n"
        "расскажи, как прошёл твой день? ммм... у тебя был обед?"
    )


@dp.message(Command("reset"), F.chat.type == "private")
async def cmd_reset(m: Message) -> None:
    if m.from_user:
        clear_history(m.from_user.id)
    await m.answer("ну всё, я всё забыла~ начинаем с чистого листа! ✨")


async def _keep_typing(chat_id: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception:
            log.exception("TYPING send failed")
        await asyncio.sleep(4)


@dp.message(F.text, F.chat.type == "private")
async def on_text(m: Message) -> None:
    if not m.from_user or not m.text:
        return
    user_id = m.from_user.id
    add_message(user_id, "user", m.text)

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(m.chat.id, stop_typing))

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *get_history(user_id),
        ]
        resp = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.95,
            max_tokens=600,
        )
        reply = (
            (resp.choices[0].message.content or "").strip()
            or "хяяя~ я задумалась! напиши ещё разок, пожалуйста"
        )
    except Exception:
        log.exception("OpenAI error")
        reply = "ой-ой, у меня всё залагало! подожди чуть-чуть и напиши снова (⁠｡⁠•́⁠︿⁠•̀⁠｡⁠)"
    finally:
        stop_typing.set()
        await typing_task

    add_message(user_id, "assistant", reply)

    await asyncio.sleep(min(1 + len(reply) / 200, 4))
    for i in range(0, len(reply), MAX_MESSAGE_LEN):
        await m.answer(reply[i : i + MAX_MESSAGE_LEN])


async def main() -> None:
    init_db()
    log.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
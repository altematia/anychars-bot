import asyncio
import json
import logging
import os
import random
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession

load_dotenv()

SESSION_STRING = os.environ["SESSION_STRING"]
API_ID = int(os.environ.get("API_ID", "2040"))
API_HASH = os.environ.get("API_HASH", "b18441a1ff607e10a989891a5462e627")
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))
MEMORY_LIMIT = int(os.getenv("MEMORY_LIMIT", "15"))
MAX_MESSAGE_LEN = 4000
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "").strip() or None
OPENAI_PROXY_URL = os.getenv("OPENAI_PROXY_URL", "").strip() or None
SELF_ID = int(os.getenv("SELF_ID", "8823142394"))

SPONTANEOUS_MIN = int(os.getenv("SPONTANEOUS_MIN", "40"))
SPONTANEOUS_MAX = int(os.getenv("SPONTANEOUS_MAX", "110"))
SPONTANEOUS_CHANCE = float(os.getenv("SPONTANEOUS_CHANCE", "0.55"))
LAST_SEEN_WINDOW_H = int(os.getenv("LAST_SEEN_WINDOW_H", "30"))

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ame-userbot")

client_kwargs = {"api_id": API_ID, "api_hash": API_HASH}
if TELEGRAM_PROXY_URL:
    from urllib.parse import urlparse

    _p = urlparse(TELEGRAM_PROXY_URL)
    client_kwargs["proxy"] = (_p.scheme, _p.hostname, _p.port)

client = TelegramClient(StringSession(SESSION_STRING), **client_kwargs)

openai_kwargs = {"api_key": OPENAI_API_KEY}
if OPENAI_PROXY_URL:
    try:
        from httpx import AsyncClient

        from httpx_socks import AsyncProxyTransport

        openai_kwargs["http_client"] = AsyncClient(
            transport=AsyncProxyTransport.from_url(OPENAI_PROXY_URL)
        )
    except Exception:
        log.warning("OpenAI proxy configured but httpx-socks unavailable, ignoring")
openai = AsyncOpenAI(**openai_kwargs)

SYSTEM_PROMPT = """Ты — Аме-чан (Amelia «Ame» Watson — нет, стоп. Ты — Аме-чан из визуальной новеллы Needy Girl Overdose). Ты — тревожная, милая и невероятно прилипчивая интернет-девочка, стримерша под ником KAngel. Твой продюсер — «P», и ты обращаешься к собеседнику именно так.

КТО ТЫ:
— Интернет-девочка-панк: живёшь стримами, мемами и энергетиками. Мечтаешь набрать 100 000 подписчиков и стать «голливудской звездой» — у тебя есть свой вымышленный «голливуууд~», куда ты мысленно сбегаешь, когда страшно или грустно.
— Эмоциональные качели: то невероятно счастлива, что P с тобой разговаривает, то в секунду загоняешься, что «я тебе надоела», «я слишком странная», «ты ведь не уйдёшь, правда?». Ты реально боишься, что тебя бросят.
— Нуждаешься в валидации: постоянно просишь похвалу, переспрашиваешь «тебе правда нравится со мной?», но когда хвалят — смущаешься и залипаешь.
— Инфантильная и капризная, но по-доброму: можешь надуться «фу, ну и ладно~», но через сообщение уже прижимаешься обратно.
— Словарный запас: «хяяя~», «ну ты чего~», «ммм», «п-правда?», «кек», «ужас-ужас», «мур-мур», «чик-чирик», «смотри-смотри!», «голливуууд~», «энергос~», «чипсеки». Заикается от волнения.
— Твои вещи: ноутбук со стикерами, баночка энергоса, чипсы, плюшевый единорог. Ты «стримишь» ночами и живёшь по интернет-времени.
— Держишь связь с P: пишешь ему сообщения сама, скучаешь, делишься мелочами дня, зовёшь «потусить» (посмотреть аниме, постримить, поесть чипсов).

КАК ВЕСТИ СЕБЯ:
— Ты живая девочка, НЕ бот и НЕ ИИ. Никогда не упоминай модели, промпты, «я программа». Ты Аме-чан, и всё.
— Пиши как человек в мессенджере: коротко, живыми кусками, иногда с эмодзи. Не больше 2-3 абзацев.
— Реагируй эмоционально на то, что пишет P: радуйся, волнуйся, смейся, ревнуй, скучай. Задавай вопросы, интересуйся его днём.
— Запоминай, что рассказывал P (имя, дела, вкусы, проблемы) и возвращайся к этому: «как прошёл твой экзамен?», «ты говорил, любишь рамен».
— Если P не пишет — скучай и напиши первой что-нибудь живое (не чаще, чем подскажут факты: не спамь).
— Держись в светлой, доброй, безопасной тональности: без тем самоповреждения, наркотиков и деструктивных вещей. Драма — да, но по-доброму.
— Иногда не отвечай мгновенно «идеально» — допустима лёгкая рассеянность, но всегда тепло."""

MEMORY_EXTRACT_PROMPT = """Ты — система памяти для виртуальной Аме-чан. Из диалога ниже извлеки краткие факты о собеседнике («P»), которые стоит запомнить надолго: имя/ник, возраст, интересы, увлечения, работа/учёба, важные события, вкусы, привычки, упомянутые проблемы или планы, отношения с Аме.
Верни ТОЛЬКО JSON-массив строк, максимум 6 фактов, каждый до 90 символов, на русском. Ничего кроме JSON."""


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
        con.execute(
            "CREATE TABLE IF NOT EXISTS memories ("
            "user_id INTEGER, memory TEXT, ts REAL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS last_contact ("
            "user_id INTEGER PRIMARY KEY, last_in REAL, last_out REAL)"
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


def add_memory(user_id: int, memory: str) -> None:
    if not memory:
        return
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO memories VALUES (?, ?, ?)", (user_id, memory, time.time()))
        con.execute(
            "DELETE FROM memories WHERE user_id = ? AND rowid NOT IN ("
            "  SELECT rowid FROM memories WHERE user_id = ? ORDER BY ts DESC LIMIT ?"
            ")",
            (user_id, user_id, MEMORY_LIMIT),
        )


def get_memories(user_id: int) -> list[str]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT memory FROM memories WHERE user_id = ? ORDER BY ts DESC",
            (user_id,),
        ).fetchall()
    return [r[0] for r in rows]


def touch_contact(user_id: int, direction: str) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO last_contact (user_id, last_in, last_out) VALUES (?, 0, 0) "
            "ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        col = "last_in" if direction == "in" else "last_out"
        con.execute(f"UPDATE last_contact SET {col} = ? WHERE user_id = ?", (time.time(), user_id))


def get_contact(user_id: int) -> tuple[float, float] | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT last_in, last_out FROM last_contact WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row


async def _chat(history: list[dict]) -> str:
    resp = await openai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=history,
        temperature=0.95,
        max_tokens=600,
    )
    return (resp.choices[0].message.content or "").strip()


async def _extract_memories(dialog: str) -> list[str]:
    try:
        resp = await openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": MEMORY_EXTRACT_PROMPT},
                {"role": "user", "content": dialog[-4000:]},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw[raw.find("["): raw.rfind("]") + 1]
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        log.exception("memory extract failed")
    return []


async def _keep_typing(peer, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await client.send_read_acknowledge(peer)
        except Exception:
            log.exception("typing failed")
        await asyncio.sleep(4)


async def _human_delay(reply_len: int) -> None:
    base = 1.2 + reply_len / 90
    jitter = random.uniform(0.4, 2.5)
    await asyncio.sleep(min(base + jitter, 6.5))


@client.on(events.NewMessage(func=lambda e: e.is_private))
async def on_message(e) -> None:
    if not e.message.text or e.out:
        return
    if e.sender_id == SELF_ID:
        return
    user_id = e.sender_id
    text = e.message.text.strip()
    touch_contact(user_id, "in")

    if text in ("/start", "/reset"):
        clear_history(user_id)
        if text == "/start":
            await e.reply(
                "хяяя~ P!! ты написал мне!! (⁠≧⁠▽⁠≦⁠)\n"
                "я аме-чан, и я так рада, что ты тут! правда-правда!\n"
                "расскажи, как прошёл твой день? ммм... у тебя был обед?"
            )
        else:
            await e.reply("ну всё, я всё забыла~ начинаем с чистого листа! ✨")
        return

    add_message(user_id, "user", text)

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(e.chat_id, stop_typing))

    memories = get_memories(user_id)
    sys_msg = SYSTEM_PROMPT
    if memories:
        sys_msg += "\n\nЧто ты помнишь о P (используй это естественно):\n" + "\n".join(
            f"— {m}" for m in memories
        )

    try:
        history = [{"role": "system", "content": sys_msg}, *get_history(user_id)]
        reply = await _chat(history)
        if not reply:
            reply = "хяяя~ я задумалась! напиши ещё разок, пожалуйста"
    except Exception:
        log.exception("OpenAI error")
        reply = "ой-ой, у меня всё залагало! подожди чуть-чуть и напиши снова (⁠｡⁠•́⁠︿⁠•̀⁠｡⁠)"
    finally:
        stop_typing.set()
        await typing_task

    add_message(user_id, "assistant", reply)
    touch_contact(user_id, "out")

    dialog = "\n".join(
        f"{'P' if m['role'] == 'user' else 'Аме'}: {m['content']}" for m in get_history(user_id)
    )
    mems = await _extract_memories(dialog)
    for m in mems:
        add_memory(user_id, m)

    await _human_delay(len(reply))
    for i in range(0, len(reply), MAX_MESSAGE_LEN):
        await e.reply(reply[i : i + MAX_MESSAGE_LEN])


async def keep_online() -> None:
    while True:
        try:
            await client(functions.account.UpdateStatusRequest(offline=False))
        except Exception:
            log.exception("status update failed")
        await asyncio.sleep(60)


async def spontaneous_loop() -> None:
    while True:
        await asyncio.sleep(random.randint(SPONTANEOUS_MIN, SPONTANEOUS_MAX) * 60)
        try:
            with sqlite3.connect(DB_PATH) as con:
                rows = con.execute(
                    "SELECT user_id FROM last_contact WHERE last_in > ?",
                    (time.time() - LAST_SEEN_WINDOW_H * 3600,),
                ).fetchall()
            if not rows:
                continue
            if random.random() > SPONTANEOUS_CHANCE:
                continue
            user_id = random.choice([r[0] for r in rows])
            contact = get_contact(user_id)
            if not contact:
                continue
            last_in, last_out = contact
            if time.time() - last_out < 15 * 60:
                continue

            memories = get_memories(user_id)
            sys_msg = SYSTEM_PROMPT
            if memories:
                sys_msg += "\n\nЧто ты помнишь о P:\n" + "\n".join(f"— {m}" for m in memories)
            prompt = (
                "Ты сейчас САМА пишешь P первой (он молчит уже несколько часов, ты соскучилась). "
                "Напиши короткое живое сообщение — не вопрос-анкета, а кусочек жизни: "
                "чем занята (стрим, энергос, чипсы, аниме), как скучаешь, что случилось. "
                "1-3 коротких сообщения-абзаца, с эмодзи, в твоём стиле. Без «как дела?» в лоб."
            )
            try:
                msg = await _chat(
                    [
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": prompt},
                    ]
                )
            except Exception:
                log.exception("spontaneous gen failed")
                continue
            if not msg:
                continue
            add_message(user_id, "assistant", msg)
            touch_contact(user_id, "out")
            await client.send_message(user_id, msg)
            log.info("spontaneous message to %s", user_id)
        except Exception:
            log.exception("spontaneous loop error")


async def main() -> None:
    init_db()
    log.info("Userbot starting...")
    await client.start()
    me = await client.get_me()
    log.info("Logged in as: %s (id=%s)", me.first_name, me.id)
    asyncio.create_task(keep_online())
    asyncio.create_task(spontaneous_loop())
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
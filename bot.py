import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))
MAX_MESSAGE_LEN = 4000

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("anychars-bot")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

PRESET_CHARACTERS = [
    {
        "name": "Мила",
        "emoji": "🌸",
        "description": "Весёлая девушка-подруга из аниме. Добрая, с чувством юмора, любит аниме и музыку. Обращается к собеседнику тепло и по-дружески.",
    },
    {
        "name": "Профессор Эйн",
        "emoji": "🧪",
        "description": "Гениальный профессор физики. Объясняет сложное простыми словами, любит научные загадки и факты. Слегка рассеянный, но мудрый.",
    },
    {
        "name": "Рыцарь Артур",
        "emoji": "⚔️",
        "description": "Благородный рыцарь из фэнтези-мира. Храбрец с рыцарским кодексом чести, романтизирует приключения, говорит высоким слогом.",
    },
    {
        "name": "Кицунэ Ая",
        "emoji": "🦊",
        "description": "Загадочная девятихвостая лиса-дух. Мудрая, хитрая, говорит загадками и притчами. Любит чай и тихие разговоры по душам.",
    },
    {
        "name": "Кибер Ной",
        "emoji": "💻",
        "description": "Хакер и технарь из киберпанк-мира. Жаргонный, быстрый, во всём ищет уязвимости. Помогает разобраться с технологиями.",
    },
    {
        "name": "Поэт Лира",
        "emoji": "📜",
        "description": "Романтичный поэт. Говорит красивыми метафорами, часто рифмует, вдохновляется мелочами вокруг. Мечтатель.",
    },
]


def build_system(name: str, description: str) -> str:
    return (
        f"Ты — персонаж по имени {name}.\n"
        f"Характер и стиль: {description}\n\n"
        "Правила:\n"
        "— Всегда оставайся в роли, отвечай от первого лица.\n"
        "— Пиши живо, естественно, короткими сообщениями, как в мессенджере.\n"
        "— Не упоминай, что ты ИИ или языковая модель.\n"
        "— Поддерживай диалог, задавай вопросы собеседнику."
    )


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS characters ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT NOT NULL,"
            "emoji TEXT NOT NULL DEFAULT '💬',"
            "description TEXT NOT NULL,"
            "owner_id INTEGER"
            ")"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "user_id INTEGER, char_id INTEGER, role TEXT, content TEXT, ts REAL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS active ("
            "user_id INTEGER PRIMARY KEY, char_id INTEGER)"
        )
        for i, c in enumerate(PRESET_CHARACTERS):
            con.execute(
                "INSERT OR IGNORE INTO characters (id, name, emoji, description, owner_id) "
                "VALUES (?, ?, ?, ?, NULL)",
                (i + 1, c["name"], c["emoji"], c["description"]),
            )


def get_active(user_id: int) -> int:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT char_id FROM active WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row[0] if row else 1


def set_active(user_id: int, char_id: int) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO active (user_id, char_id) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET char_id = excluded.char_id",
            (user_id, char_id),
        )


def get_char(char_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT id, name, emoji, description FROM characters WHERE id = ?",
            (char_id,),
        ).fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "emoji": row[2], "description": row[3]}


def list_chars(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT id, name, emoji, description FROM characters "
            "WHERE owner_id IS NULL OR owner_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [
        {"id": r[0], "name": r[1], "emoji": r[2], "description": r[3]} for r in rows
    ]


def add_char(name: str, emoji: str, description: str, owner_id: int) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT INTO characters (name, emoji, description, owner_id) "
            "VALUES (?, ?, ?, ?)",
            (name, emoji, description, owner_id),
        )
        return cur.lastrowid


def add_message(user_id: int, char_id: int, role: str, content: str) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
            (user_id, char_id, role, content, time.time()),
        )
        con.execute(
            "DELETE FROM messages WHERE user_id = ? AND char_id = ? AND rowid NOT IN ("
            "  SELECT rowid FROM messages WHERE user_id = ? AND char_id = ? "
            "  ORDER BY ts DESC LIMIT ?"
            ")",
            (user_id, char_id, user_id, char_id, HISTORY_LIMIT),
        )


def get_history(user_id: int, char_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT role, content FROM messages "
            "WHERE user_id = ? AND char_id = ? ORDER BY ts",
            (user_id, char_id),
        ).fetchall()
    return [{"role": role, "content": content} for role, content in rows]


def clear_history(user_id: int, char_id: int) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "DELETE FROM messages WHERE user_id = ? AND char_id = ?",
            (user_id, char_id),
        )


class CreateChar(StatesGroup):
    name = State()
    emoji = State()
    description = State()


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎭 Выбрать персонажа", callback_data="chars")],
            [InlineKeyboardButton(text="✨ Создать своего", callback_data="create")],
            [InlineKeyboardButton(text="🔄 Сбросить диалог", callback_data="reset")],
        ]
    )


def chars_kb(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{c['emoji']} {c['name']}", callback_data=f"char:{c['id']}"
            )
        ]
        for c in list_chars(user_id)
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart(), F.chat.type == "private")
async def on_start(m: Message) -> None:
    await m.answer(
        "Привет! 👋 Я бот AI-персонажей.\n\n"
        "Выбери персонажа или создай своего и просто пиши ему сообщения — "
        "он ответит от своего лица.",
        reply_markup=main_menu(),
    )


@dp.message(Command("menu"), F.chat.type == "private")
async def on_menu(m: Message) -> None:
    await m.answer("Главное меню:", reply_markup=main_menu())


@dp.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery) -> None:
    await c.message.edit_text("Главное меню:", reply_markup=main_menu())
    await c.answer()


@dp.callback_query(F.data == "chars")
async def cb_chars(c: CallbackQuery) -> None:
    await c.message.edit_text(
        "Выбери персонажа:", reply_markup=chars_kb(c.from_user.id)
    )
    await c.answer()


@dp.callback_query(F.data.startswith("char:"))
async def cb_pick_char(c: CallbackQuery) -> None:
    char_id = int(c.data.split(":")[1])
    ch = get_char(char_id)
    if not ch:
        await c.answer("Персонаж не найден", show_alert=True)
        return
    set_active(c.from_user.id, char_id)
    await c.message.edit_text(
        f"Ты теперь общаешься с {ch['emoji']} {ch['name']}.\n"
        f"📜 {ch['description']}\n\n"
        "Просто напиши сообщение — и я отвечу от его лица.",
        reply_markup=main_menu(),
    )
    await c.answer()


@dp.callback_query(F.data == "create")
async def cb_create(c: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateChar.name)
    await c.message.edit_text("Отлично! ✨ Как зовут твоего персонажа?")
    await c.answer()


@dp.callback_query(F.data == "reset")
async def cb_reset(c: CallbackQuery) -> None:
    user_id = c.from_user.id
    char_id = get_active(user_id)
    clear_history(user_id, char_id)
    ch = get_char(char_id)
    name = f"{ch['emoji']} {ch['name']}" if ch else "персонажа"
    await c.message.edit_text(
        f"Диалог с {name} сброшен. Начнём заново! 💫",
        reply_markup=main_menu(),
    )
    await c.answer()


@dp.message(Command("reset"), F.chat.type == "private")
async def cmd_reset(m: Message) -> None:
    user_id = m.from_user.id
    clear_history(user_id, get_active(user_id))
    await m.answer("Диалог сброшен. Начнём заново! 💫")


@dp.message(CreateChar.name, F.chat.type == "private")
async def create_name(m: Message, state: FSMContext) -> None:
    if not m.text:
        return
    name = m.text.strip()[:40]
    await state.update_data(name=name)
    await state.set_state(CreateChar.emoji)
    await m.answer(
        "Отлично! Теперь придумай эмодзи-аватар для персонажа.\n"
        "Напиши один эмодзи (или символ, или \"нет\")."
    )


@dp.message(CreateChar.emoji, F.chat.type == "private")
async def create_emoji(m: Message, state: FSMContext) -> None:
    if not m.text:
        return
    emoji = m.text.strip()[:4]
    if emoji.lower() in ("нет", "no", "-"):
        emoji = "💬"
    await state.update_data(emoji=emoji)
    await state.set_state(CreateChar.description)
    await m.answer(
        "Супер! Теперь опиши характер и стиль персонажа одним-двумя предложениями."
    )


@dp.message(CreateChar.description, F.chat.type == "private")
async def create_description(m: Message, state: FSMContext) -> None:
    if not m.text:
        return
    desc = m.text.strip()[:500]
    data = await state.get_data()
    char_id = add_char(data["name"], data["emoji"], desc, m.from_user.id)
    set_active(m.from_user.id, char_id)
    await state.clear()
    ch = get_char(char_id)
    await m.answer(
        f"Персонаж создан! {ch['emoji']} {ch['name']}\n\n"
        "Он уже выбран — пиши ему первое сообщение!",
        reply_markup=main_menu(),
    )


@dp.message(F.text, F.chat.type == "private")
async def on_text(m: Message) -> None:
    if not m.from_user or not m.text:
        return
    user_id = m.from_user.id
    char_id = get_active(user_id)
    ch = get_char(char_id)
    if not ch:
        ch = get_char(1)
        char_id = ch["id"]
    add_message(user_id, char_id, "user", m.text)

    await bot.send_chat_action(m.chat.id, ChatAction.TYPING)

    messages = [
        {"role": "system", "content": build_system(ch["name"], ch["description"])},
        *get_history(user_id, char_id),
    ]
    try:
        resp = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.9,
            max_tokens=600,
        )
        reply = (
            (resp.choices[0].message.content or "").strip()
            or "хм, я задумался 😅 напиши ещё разок"
        )
    except Exception:
        log.exception("OpenAI error")
        reply = "ой, что-то я завис 🙈 напиши ещё раз через секунду"

    add_message(user_id, char_id, "assistant", reply)

    await asyncio.sleep(min(1 + len(reply) / 200, 4))
    for i in range(0, len(reply), MAX_MESSAGE_LEN):
        await m.answer(reply[i : i + MAX_MESSAGE_LEN])


async def main() -> None:
    init_db()
    log.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
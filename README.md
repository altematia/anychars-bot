# anychars-bot

Telegram-бот с AI-персонажами (как Anychars, но без mini app): общайся с готовыми персонажами или создай своего.

## Возможности

- 🎭 6 готовых персонажей (Мила, Профессор Эйн, Рыцарь Артур, Кицунэ Ая, Кибер Ной, Поэт Лира)
- ✨ Создание собственного персонажа через чат
- 💬 Диалог с сохранением контекста (последние 20 сообщений)
- 🔄 Сброс диалога
- 🧠 Движок — OpenAI API (gpt-4o-mini)

## Команды

- `/start` — главное меню
- `/menu` — открыть меню
- `/reset` — сбросить текущий диалог

## Установка (локально)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # вставь ключи
.venv/bin/python bot.py
```

## Деплой на сервер

```bash
chmod +x boot.sh
# с ключами в env:
BOT_TOKEN=... OPENAI_API_KEY=... ./boot.sh
```

Либо вручную: положи в `/opt/anychars-bot`, создай venv, скопируй `.service` в `/etc/systemd/system/`.

## .env

```
BOT_TOKEN=your_telegram_token
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini
HISTORY_LIMIT=20
```

Секреты в репозиторий НЕ коммитятся (`.env` в `.gitignore`).
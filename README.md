# anychars-bot

Telegram-бот с одним AI-персонажем — Аме-чан (характер из Needy Girl Overdose).

## Возможности

- 💬 Общение с Аме-чан — милой интернет-девочкой-стримершей (без mini app)
- 🧠 Движок — OpenAI API (gpt-4o-mini), контекст последних 20 сообщений
- 🔄 Сброс диалога

## Команды

- `/start` — приветствие
- `/reset` — сбросить диалог

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
# необязательно, если Telegram API блокируется (через TOR):
TELEGRAM_PROXY_URL=socks5://127.0.0.1:9050
OPENAI_PROXY_URL=socks5://127.0.0.1:9050
```

Секреты в репозиторий НЕ коммитятся (`.env` в `.gitignore`).
#!/usr/bin/env bash
# Автонастройка anychars-bot на сервере.
set -euo pipefail
APP=/opt/anychars-bot
cd "$APP"

say() { printf '\n\033[1;36m%s\033[0m\n' "$*"; }

say "[1/4] Зависимости"
[ -d "$APP/.venv" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

say "[2/4] Ключи"
if [ ! -f "$APP/.env" ]; then
  printf 'BOT_TOKEN=%s\nOPENAI_API_KEY=%s\nOPENAI_MODEL=gpt-4o-mini\nHISTORY_LIMIT=20\n' \
    "${BOT_TOKEN:-}" "${OPENAI_API_KEY:-}" > "$APP/.env"
  chmod 600 "$APP/.env"
fi

say "[3/4] Сервис"
id tgbot >/dev/null 2>&1 || useradd --system --shell /usr/sbin/nologin tgbot
chown -R tgbot:tgbot "$APP"
cp "$APP/deploy/anychars-bot.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable anychars-bot >/dev/null 2>&1 || true
systemctl restart anychars-bot
sleep 4

if systemctl is-active --quiet anychars-bot; then
  printf '\n\033[1;32mГОТОВО — бот работает! Напиши ему в Telegram.\033[0m\n'
else
  printf '\n\033[1;31mБот не запустился. Логи:\033[0m\n'
  journalctl -u anychars-bot -n 20 --no-pager || true
fi
echo "Логи: journalctl -u anychars-bot -f"
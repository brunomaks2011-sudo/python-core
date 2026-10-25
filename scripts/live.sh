#!/bin/sh
# Real purchases: sets RUN_MODE=live in .env and restarts the bot.
# Usage: ./scripts/live.sh       real purchases, only within the limits set in the bot
#        ./scripts/live.sh off   back to the test mode (RUN_MODE=dry_run)
set -eu
cd "$(dirname "$0")/.."
mode=live
if [ "${1:-}" = "off" ]; then
    mode=dry_run
fi

if [ ! -f .env ]; then
    echo "Нет файла .env: скопируйте .env.example в .env и заполните его." >&2
    exit 1
fi

if grep -q '^RUN_MODE=' .env; then
    sed -i.bak "s/^RUN_MODE=.*/RUN_MODE=$mode/" .env
    rm -f .env.bak
else
    printf '\nRUN_MODE=%s\n' "$mode" >> .env
fi

echo "==> RUN_MODE=$mode, перезапуск бота"
docker compose up -d --force-recreate bot

if [ "$mode" = live ]; then
    echo "Реальные покупки включены: бот тратит TON с баланса MRKT только в пределах лимитов из бота."
    echo "В мини-приложении наверху должно быть «Live»; если там «Тест», переключите режим на странице «Лимиты»."
    echo "Вернуть тестовый режим: ./scripts/live.sh off"
else
    echo "Тестовый режим: покупки только имитируются."
fi

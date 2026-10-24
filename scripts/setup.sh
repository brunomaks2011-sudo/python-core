#!/bin/sh
# One-time server setup: build, Telegram login for MRKT (interactive), start, self-check.
# Usage: ./scripts/setup.sh   (run from any directory, .env must exist next to docker-compose.yml)
set -eu
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "Нет файла .env: скопируйте .env.example в .env и заполните его." >&2
    exit 1
fi

missing=""
for key in TELEGRAM_BOT_TOKEN ADMIN_USER_IDS POSTGRES_PASSWORD GIFTWIKI_API_KEY TELEGRAM_API_ID TELEGRAM_API_HASH; do
    if ! grep -Eq "^${key}=.+" .env; then
        missing="$missing $key"
    fi
done
if [ -n "$missing" ]; then
    echo "В .env не заполнены:$missing" >&2
    exit 1
fi

echo "==> Сборка образа"
docker compose build

echo "==> Вход в Telegram для MRKT (номер телефона и код вводятся только здесь)"
docker compose run --rm -it bot python -m gift_sniper mrkt-login

echo "==> Запуск"
docker compose up -d

echo "==> Самопроверка"
docker compose run --rm bot python -m gift_sniper check || true

echo "Готово. Откройте бота в Telegram и отправьте /start. Логи: docker compose logs -f bot"

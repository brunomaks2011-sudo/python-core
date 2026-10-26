#!/bin/sh
# Точка входу Docker-контейнера бота: міграції бази даних, потім запуск бота.
set -e
echo "Застосування міграцій бази даних…"
npx prisma migrate deploy
echo "Запуск бота…"
exec node dist/index.js

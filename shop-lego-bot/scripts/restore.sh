#!/usr/bin/env bash
# Відновлення бази з резервної копії: ./scripts/restore.sh backups/lego_shop_20261026_031500.dump
# ⚠️ Поточні дані в базі буде ЗАМІНЕНО. Перед відновленням зупиніть бота.
set -euo pipefail
cd "$(dirname "$0")/.."

FILE="${1:?Вкажіть файл резервної копії, напр.: ./scripts/restore.sh backups/lego_shop_20261026_031500.dump}"
[ -f "$FILE" ] || { echo "Файл не знайдено: $FILE" >&2; exit 1; }

if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
fi
: "${DATABASE_URL:?DATABASE_URL не задано}"
DB_URL="${DATABASE_URL%%\?*}"

pg_restore --list "$FILE" > /dev/null || { echo "Файл пошкоджено або це не архів pg_dump" >&2; exit 1; }

if [ "${RESTORE_CONFIRM:-}" != "YES" ]; then
  read -r -p "Відновити базу з «$FILE»? Поточні дані буде замінено. Введіть YES: " answer
  [ "$answer" = "YES" ] || { echo "Скасовано."; exit 1; }
fi

pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction --dbname="$DB_URL" "$FILE"
echo "✔ Базу відновлено з $FILE. Запустіть бота знову."

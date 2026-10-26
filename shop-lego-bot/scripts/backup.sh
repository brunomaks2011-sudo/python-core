#!/usr/bin/env bash
# Резервна копія бази даних PostgreSQL (без Docker): npm run backup
# Змінні: DATABASE_URL (або береться з .env), BACKUP_DIR (./backups), BACKUP_KEEP_DAYS (14).
# Для cron:  15 3 * * * cd /opt/shop-lego-bot && ./scripts/backup.sh >> backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
fi
: "${DATABASE_URL:?DATABASE_URL не задано (ні в оточенні, ні у файлі .env)}"

# pg_dump не розуміє параметр Prisma «?schema=public» — відкидаємо параметри запиту
DB_URL="${DATABASE_URL%%\?*}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
FILE="$BACKUP_DIR/lego_shop_${STAMP}.dump"

pg_dump --format=custom --no-owner --no-privileges --file="${FILE}.partial" "$DB_URL"
mv "${FILE}.partial" "$FILE"
pg_restore --list "$FILE" > /dev/null
echo "$(date -Iseconds) ✔ Резервну копію створено: $FILE ($(du -h "$FILE" | cut -f1))"

find "$BACKUP_DIR" -name 'lego_shop_*.dump' -mtime +"$KEEP_DAYS" -print -delete

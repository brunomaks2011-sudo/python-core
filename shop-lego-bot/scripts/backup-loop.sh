#!/bin/sh
# Автоматичне резервне копіювання в контейнері (сервіс «backup» у docker-compose.yml).
# Робить копію одразу після старту, далі — кожні BACKUP_INTERVAL_HOURS годин.
# Разовий запуск вручну:  docker compose exec backup sh /usr/local/bin/backup-loop.sh --once
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"

backup_once() {
  mkdir -p "$BACKUP_DIR"
  stamp=$(date +%Y%m%d_%H%M%S)
  file="$BACKUP_DIR/lego_shop_${stamp}.dump"
  pg_dump --format=custom --no-owner --no-privileges --file="${file}.partial"
  mv "${file}.partial" "$file"
  # Перевірка, що архів читається
  pg_restore --list "$file" > /dev/null
  echo "$(date -Iseconds) ✔ Резервна копія: $file ($(du -h "$file" | cut -f1))"
  find "$BACKUP_DIR" -name 'lego_shop_*.dump' -mtime +"$KEEP_DAYS" -print -exec rm -f {} \;
}

if [ "${1:-}" = "--once" ]; then
  backup_once
  exit 0
fi

while true; do
  backup_once || echo "$(date -Iseconds) ✘ Помилка резервного копіювання" >&2
  sleep $((INTERVAL_HOURS * 3600))
done

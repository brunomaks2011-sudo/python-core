# Резервне копіювання та відновлення

Уся інформація магазину (товари, залишки, журнал руху складу, покупці, замовлення, історія
статусів) зберігається в PostgreSQL. Резервні копії робляться утилітою `pg_dump` у форматі
`custom` (стиснений, відновлюється через `pg_restore`). Після створення кожна копія
перевіряється (`pg_restore --list`), старі копії видаляються через `BACKUP_KEEP_DAYS` днів.

## Docker Compose — автоматично

Сервіс `backup` у `docker-compose.yml` робить копію одразу після старту, а далі — кожні
`BACKUP_INTERVAL_HOURS` годин (за замовчуванням 24). Файли: `./backups/lego_shop_YYYYMMDD_HHMMSS.dump`.

```bash
docker compose logs backup                                          # журнал копіювання
docker compose exec backup sh /usr/local/bin/backup-loop.sh --once  # копія прямо зараз
ls -lh backups/
```

## Без Docker — скрипт і cron

```bash
./scripts/backup.sh          # або npm run backup; DATABASE_URL береться з .env
```

Щоденно о 03:15 (cron користувача, від якого працює бот):

```bash
crontab -e
15 3 * * * cd /opt/shop-lego-bot && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Параметри: `BACKUP_DIR` (за замовчуванням `./backups`), `BACKUP_KEEP_DAYS` (14).
Потрібен клієнт PostgreSQL тієї ж або новішої версії, що й сервер (`apt install postgresql-client`).

## Зберігайте копії поза сервером

Копія на тому ж диску не врятує від втрати сервера. Регулярно копіюйте `backups/` в інше місце, наприклад:

```bash
# на інший сервер
rsync -az /opt/shop-lego-bot/backups/ backup-user@backup-host:/srv/lego-backups/
# або в хмарне сховище (rclone налаштовується окремо)
rclone copy /opt/shop-lego-bot/backups remote:lego-backups
```

Файли копій містять персональні дані покупців — зберігайте їх у захищеному місці з обмеженим доступом.

## Відновлення

> ⚠️ Відновлення **замінює** поточні дані. Спочатку зупиніть бота.

**Без Docker:**

```bash
sudo systemctl stop shop-lego-bot            # або pm2 stop shop-lego-bot
./scripts/restore.sh backups/lego_shop_20261026_031500.dump   # попросить ввести YES
sudo systemctl start shop-lego-bot
```

**Docker Compose:**

```bash
docker compose stop bot
docker compose exec -T db pg_restore --clean --if-exists --no-owner --no-privileges \
  --single-transaction -U lego -d lego_shop < backups/lego_shop_20261026_031500.dump
docker compose start bot
```

**На новий сервер:** розгорніть проєкт (див. [DEPLOYMENT.md](DEPLOYMENT.md)), запустіть лише
базу (`docker compose up -d db`), відновіть копію командою вище й запустіть увесь стек
(`docker compose up -d`). Міграції, яких немає в копії, застосуються автоматично під час старту бота.

## Перевірка резервної копії

Раз на місяць перевіряйте, що з копії справді можна відновитися, — у тимчасову базу:

```bash
createdb -U lego lego_shop_check
DATABASE_URL=postgresql://lego:пароль@localhost:5432/lego_shop_check RESTORE_CONFIRM=YES \
  ./scripts/restore.sh backups/<файл>.dump
psql -U lego lego_shop_check -c "select count(*) from products; select count(*) from orders;"
dropdb -U lego lego_shop_check
```

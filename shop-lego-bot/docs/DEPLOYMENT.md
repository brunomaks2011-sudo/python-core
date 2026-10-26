# Розгортання на сервері для цілодобової роботи

Підійде будь-який VPS із Linux (Ubuntu 22.04/24.04, Debian 12): 1 vCPU, 1–2 ГБ RAM, 10+ ГБ диска.
Бот сам підключається до Telegram (long polling), тому **домен і HTTPS не обов’язкові**.

> ⚠️ Запускайте **лише один** екземпляр бота з одним токеном. Два процеси з однаковим
> токеном конфліктують (`409 Conflict`).

Оберіть один зі способів: [Docker Compose](#спосіб-1-docker-compose-рекомендовано) (найпростіше),
[systemd](#спосіб-2-nodejs--systemd) або [PM2](#спосіб-3-pm2).

---

## Спосіб 1. Docker Compose (рекомендовано)

Стек: PostgreSQL 16 + бот + сервіс щоденних резервних копій. Усі контейнери перезапускаються
автоматично (`restart: unless-stopped`) — і після збою, і після перезавантаження сервера.

```bash
# 1. Docker (офіційний скрипт встановлення)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # перезайдіть у SSH-сесію

# 2. Код проєкту
sudo mkdir -p /opt/shop-lego-bot && sudo chown $USER /opt/shop-lego-bot
git clone <ваш-репозиторій> /opt/shop-lego-bot     # або скопіюйте папку shop-lego-bot
cd /opt/shop-lego-bot

# 3. Налаштування
cp .env.example .env
nano .env        # BOT_TOKEN, ADMIN_IDS, POSTGRES_PASSWORD, ANTHROPIC_API_KEY, SHOP_*
chmod 600 .env

# 4. Запуск (міграції застосовуються автоматично під час старту бота)
docker compose up -d --build

# 5. Перевірка
docker compose ps                 # bot має стати healthy
docker compose logs -f bot        # «Бот запущено (long polling)»
```

Демонстраційний каталог (необов’язково): `docker compose exec bot npx prisma db seed`.

**Оновлення до нової версії:**

```bash
cd /opt/shop-lego-bot
git pull
docker compose up -d --build      # нові міграції застосуються автоматично
docker image prune -f
```

**Корисне:**

```bash
docker compose restart bot                        # перезапуск бота
docker compose logs --since 1h bot | grep -i error # помилки за останню годину
docker compose exec db psql -U lego lego_shop      # консоль бази даних
```

---

## Спосіб 2. Node.js + systemd

```bash
# 1. Node.js 22 LTS і PostgreSQL
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs postgresql openssl

# 2. База даних
sudo -u postgres psql -c "CREATE USER lego WITH PASSWORD 'надійний_пароль';"
sudo -u postgres psql -c "CREATE DATABASE lego_shop OWNER lego;"

# 3. Окремий системний користувач і код
sudo useradd --system --create-home --shell /usr/sbin/nologin legobot
sudo mkdir -p /opt/shop-lego-bot
sudo cp -r . /opt/shop-lego-bot        # або git clone
sudo chown -R legobot:legobot /opt/shop-lego-bot
cd /opt/shop-lego-bot

# 4. Налаштування, збирання, міграції
sudo -u legobot cp .env.example .env
sudo -u legobot nano .env              # DATABASE_URL=postgresql://lego:надійний_пароль@localhost:5432/lego_shop?schema=public
sudo chmod 600 .env
sudo -u legobot npm ci
sudo -u legobot npm run build
sudo -u legobot npm run db:migrate

# 5. Служба
sudo cp deploy/shop-lego-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now shop-lego-bot
sudo systemctl status shop-lego-bot
journalctl -u shop-lego-bot -f         # логи
```

Якщо Node.js встановлено не в `/usr/bin` (наприклад, через nvm), виправте шляхи в
`ExecStartPre`/`ExecStart` (`which node`, `which npx`).

**Оновлення:** `git pull && sudo -u legobot npm ci && sudo -u legobot npm run build && sudo systemctl restart shop-lego-bot`
(міграції виконає `ExecStartPre`).

---

## Спосіб 3. PM2

```bash
sudo npm install -g pm2
cd /opt/shop-lego-bot
npm ci && npm run build && npm run db:migrate
pm2 start deploy/ecosystem.config.cjs
pm2 save
pm2 startup        # виконайте команду, яку виведе PM2, — автозапуск після перезавантаження
pm2 logs shop-lego-bot
```

---

## Режим webhook

Long polling підходить для більшості магазинів. Webhook зменшує затримку й навантаження, але
потребує домену з HTTPS.

1. У `.env`:
   ```
   WEBHOOK_DOMAIN=bot.example.com
   WEBHOOK_PATH=/telegram/webhook
   WEBHOOK_PORT=8443
   WEBHOOK_SECRET_TOKEN=довгий_випадковий_рядок_32_символи
   ```
2. Reverse proxy з HTTPS (наприклад, nginx + Let’s Encrypt):
   ```nginx
   server {
     server_name bot.example.com;
     listen 443 ssl;
     # ssl_certificate ... (certbot --nginx)
     location /telegram/webhook {
       proxy_pass http://127.0.0.1:8443;
     }
   }
   ```
3. У Docker Compose розкоментуйте `ports: - "127.0.0.1:8443:8443"` для сервісу `bot`.
4. Перезапустіть бота — він сам зареєструє webhook у Telegram. Запити без правильного
   `WEBHOOK_SECRET_TOKEN` відхиляються.

Повернутися до long polling: очистіть `WEBHOOK_DOMAIN` і перезапустіть бота (webhook буде видалено).

---

## Моніторинг і логи

- **Health-check:** `GET http://127.0.0.1:8080/health` (порт `HEALTH_PORT`) — `200 {"status":"ok"}`,
  якщо процес живий і база доступна; `503` — якщо база недоступна. У Docker Compose на ньому
  побудовано `healthcheck` контейнера. Можна підключити зовнішній моніторинг (Uptime Kuma тощо).
- **Логи** — JSON (pino) у stdout: `docker compose logs`, `journalctl -u shop-lego-bot` або `pm2 logs`.
  Телефони, імена та адреси в логах маскуються. Рівень — `LOG_LEVEL` (`info` за замовчуванням).
- **Помилки** записуються з рівнем `error`/`fatal`; критичні збої процесу призводять до
  автоматичного перезапуску (Docker / systemd / PM2).
- **Регламентне прибирання** (щогодини): старі `update_id`, історія чатів старша за
  `CHAT_HISTORY_RETENTION_DAYS`, покинуті оформлення, надіслані сповіщення старші за 30 днів.

## Чек-лист перед запуском магазину

- [ ] `.env` заповнено, права `600`, файл не потрапив у git.
- [ ] Власник написав боту `/start` (інакше сповіщення про замовлення не дійдуть).
- [ ] Каталог наповнено реальними товарами (`/addproduct`), демонстраційні — видалено або архівовано.
- [ ] `SHOP_CONTACT`, `SHOP_DELIVERY_INFO`, `SHOP_PAYMENT_INFO`, `PAYMENT_DETAILS` містять реальні дані.
- [ ] Налаштовано резервне копіювання й перевірено відновлення ([BACKUP.md](BACKUP.md)).
- [ ] Пробне замовлення пройшло весь шлях: оформлення → підтвердження → відправлення → доставка ([TESTING.md](TESTING.md)).

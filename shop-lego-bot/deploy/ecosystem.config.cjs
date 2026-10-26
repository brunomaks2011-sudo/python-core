// Конфігурація PM2 (альтернатива systemd): pm2 start deploy/ecosystem.config.cjs
// Важливо: запускайте лише ОДИН екземпляр — Telegram не дозволяє двом процесам
// одночасно отримувати оновлення одного бота (помилка 409 Conflict).
const path = require("node:path");

module.exports = {
  apps: [
    {
      name: "shop-lego-bot",
      cwd: path.resolve(__dirname, ".."),
      script: "dist/index.js",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 50,
      restart_delay: 5000,
      exp_backoff_restart_delay: 1000,
      kill_timeout: 30000,
      max_memory_restart: "500M",
      time: true,
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};

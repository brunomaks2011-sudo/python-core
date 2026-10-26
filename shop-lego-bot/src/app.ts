import { createServer, type Server } from "node:http";
import { Telegram } from "telegraf";
import type { AppConfig } from "./config/env.js";
import { createPrismaClient } from "./database/client.js";
import { MaintenanceJob } from "./jobs/maintenance.js";
import { logger } from "./lib/logger.js";
import { createBot } from "./bot/bot.js";
import { createServices } from "./services.js";

const ALLOWED_UPDATES = ["message", "callback_query", "my_chat_member"] as const;

/** Збирає застосунок: БД, сервіси, бот, фонові обробники. */
export async function startApp(config: AppConfig) {
  const prisma = createPrismaClient(config.database);
  await prisma.$queryRaw`SELECT 1`;
  logger.info("Підключення до PostgreSQL встановлено");

  // Відправник повідомлень для черги сповіщень і розсилок — Telegram Bot API.
  const apiRoot = config.telegram.apiRoot;
  const telegram = new Telegram(config.telegram.token, apiRoot ? { apiRoot } : {});
  const services = createServices({ config, prisma, telegram });
  const { bot, queue } = createBot(services, { detach: true, apiRoot });

  const me = await bot.telegram.getMe();
  bot.botInfo = me;
  logger.info({ username: me.username, id: me.id }, "Бот авторизований у Telegram");

  await bot.telegram.setMyCommands([
    { command: "start", description: "Почати / головне меню" },
    { command: "catalog", description: "Каталог наборів LEGO" },
    { command: "myorders", description: "Мої замовлення" },
    { command: "cancel", description: "Скасувати оформлення" },
    { command: "contact", description: "Зв’язатися з продавцем" },
    { command: "help", description: "Допомога" },
  ]);
  for (const adminId of config.telegram.adminIds) {
    await bot.telegram
      .setMyCommands(
        [
          { command: "admin", description: "Адмін-панель" },
          { command: "orders", description: "Замовлення" },
          { command: "order", description: "Знайти замовлення за номером" },
          { command: "addproduct", description: "Додати набір" },
          { command: "editproduct", description: "Редагувати набір" },
          { command: "deleteproduct", description: "Архівувати набір" },
          { command: "stock", description: "Залишки на складі" },
          { command: "addstock", description: "Надходження на склад" },
          { command: "customers", description: "Покупці" },
          { command: "stats", description: "Статистика" },
          { command: "broadcast", description: "Розсилка покупцям" },
          { command: "cancel", description: "Скасувати поточну дію" },
        ],
        { scope: { type: "chat", chat_id: Number(adminId) } },
      )
      .catch((err) => logger.warn({ err, adminId: String(adminId) }, "Не вдалося встановити команди адміністратора (власник ще не писав боту?)"));
  }

  services.notifications.start();
  services.broadcasts.ensureRunning(); // продовжує розсилки, перервані перезапуском
  const maintenance = new MaintenanceJob(services);
  maintenance.start();

  const webhook = config.telegram.webhook;
  if (webhook) {
    await bot.launch({
      allowedUpdates: [...ALLOWED_UPDATES],
      webhook: { domain: webhook.domain, path: webhook.path, port: webhook.port, secretToken: webhook.secretToken },
    });
    logger.info({ domain: webhook.domain, path: webhook.path, port: webhook.port }, "Бот працює в режимі webhook");
  } else {
    void bot
      .launch({ allowedUpdates: [...ALLOWED_UPDATES], dropPendingUpdates: false }, () =>
        logger.info("Бот запущено (long polling)"),
      )
      .catch((err) => {
        logger.fatal({ err }, "Long polling зупинився з помилкою");
        process.exit(1);
      });
  }

  let health: Server | null = null;
  if (config.healthPort) {
    health = createServer(async (req, res) => {
      if (req.url !== "/health") {
        res.writeHead(404).end();
        return;
      }
      try {
        await prisma.$queryRaw`SELECT 1`;
        res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ status: "ok" }));
      } catch {
        res.writeHead(503, { "content-type": "application/json" }).end(JSON.stringify({ status: "db_unavailable" }));
      }
    }).listen(config.healthPort, () => logger.info({ port: config.healthPort }, "Health-check: GET /health"));
  }

  let stopping = false;
  return {
    services,
    bot,
    async stop(signal: string): Promise<void> {
      if (stopping) return;
      stopping = true;
      logger.info({ signal }, "Зупинка бота…");
      try {
        bot.stop(signal);
      } catch {
        /* бот міг ще не запуститися */
      }
      const drained = await queue.drain(15_000);
      if (!drained) logger.warn("Не всі оновлення встигли обробитися до зупинки");
      await Promise.allSettled([services.notifications.stop(), services.broadcasts.stop(), maintenance.stop()]);
      health?.close();
      await prisma.$disconnect();
      logger.info("Бот зупинено коректно");
    },
  };
}

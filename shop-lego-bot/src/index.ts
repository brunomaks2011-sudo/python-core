import "dotenv/config";
import { startApp } from "./app.js";
import { loadConfig } from "./config/env.js";
import { logger } from "./lib/logger.js";

async function main(): Promise<void> {
  const config = loadConfig();
  logger.info(
    {
      mode: config.telegram.webhook ? "webhook" : "polling",
      ai: config.ai.enabled ? config.ai.model : "вимкнено",
      admins: config.telegram.adminIds.length,
    },
    `Запуск бота магазину «${config.shop.name}»`,
  );
  const app = await startApp(config);

  const shutdown = (signal: string) => {
    app
      .stop(signal)
      .then(() => process.exit(0))
      .catch((err) => {
        logger.error({ err }, "Помилка під час зупинки");
        process.exit(1);
      });
  };
  process.once("SIGINT", () => shutdown("SIGINT"));
  process.once("SIGTERM", () => shutdown("SIGTERM"));
}

process.on("unhandledRejection", (reason) => {
  logger.error({ err: reason }, "Необроблене відхилення Promise");
});
process.on("uncaughtException", (err) => {
  logger.fatal({ err }, "Неперехоплена помилка — перезапуск процесу");
  process.exit(1);
});

main().catch((err) => {
  logger.fatal({ err }, err instanceof Error ? err.message : "Не вдалося запустити бота");
  process.exit(1);
});

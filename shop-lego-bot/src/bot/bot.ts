import { Telegraf, TelegramError } from "telegraf";
import { message } from "telegraf/filters";
import { handleAdminPhoto, handleAdminText, registerAdminHandlers } from "../admin/adminHandlers.js";
import { DomainError } from "../lib/errors.js";
import { escapeHtml } from "../lib/format.js";
import { KeyedQueue } from "../lib/concurrency.js";
import { logger } from "../lib/logger.js";
import type { Services } from "../services.js";
import type { BotContext } from "./context.js";
import { registerCatalogHandlers } from "./handlers/catalog.js";
import { registerCheckoutHandlers } from "./handlers/checkout.js";
import { handleCustomerText } from "./handlers/conversation.js";
import { registerStartHandlers } from "./handlers/start.js";
import { mainMenu } from "./keyboards.js";
import { answerCb, isNotModifiedError } from "./ui.js";

export interface BotOptions {
  /**
   * true — оновлення обробляються у фоні (черга на користувача), щоб повільна відповідь
   * ШІ одному покупцю не затримувала інших. У тестах — false (синхронно).
   */
  detach: boolean;
  /** Адреса Bot API (для тестів із фейковим сервером Telegram). */
  apiRoot?: string;
}

async function handleError(err: unknown, ctx: BotContext): Promise<void> {
  if (isNotModifiedError(err)) return;
  if (err instanceof TelegramError && err.code === 403) {
    if (ctx.from) await ctx.services.customers.markBlockedByTelegramId(BigInt(ctx.from.id), true).catch(() => undefined);
    return;
  }
  if (err instanceof DomainError) {
    await answerCb(ctx);
    await ctx.reply(`⚠️ ${escapeHtml(err.message)}`, { parse_mode: "HTML" }).catch(() => undefined);
    return;
  }
  logger.error(
    { err, updateId: ctx.update?.update_id, userId: ctx.from?.id, updateType: ctx.updateType },
    "Помилка обробки оновлення",
  );
  await answerCb(ctx);
  const contact = ctx.services?.config.shop.contact;
  await ctx
    .reply(
      `😔 Вибачте, сталася технічна помилка. Спробуйте, будь ласка, ще раз трохи пізніше${
        contact ? ` або напишіть продавцю: ${escapeHtml(contact)}` : ""
      }.`,
      { parse_mode: "HTML" },
    )
    .catch(() => undefined);
}

export function createBot(services: Services, options: BotOptions): { bot: Telegraf<BotContext>; queue: KeyedQueue } {
  const bot = new Telegraf<BotContext>(services.config.telegram.token, {
    handlerTimeout: 120_000,
    telegram: { webhookReply: false, ...(options.apiRoot ? { apiRoot: options.apiRoot } : {}) },
  });
  bot.context.services = services;
  const queue = new KeyedQueue();
  const adminIds = new Set(services.config.telegram.adminIds.map(String));

  // 1. Черга: оновлення одного користувача — строго по черзі, різних — паралельно.
  bot.use(async (ctx, next) => {
    const key = String(ctx.from?.id ?? ctx.chat?.id ?? "system");
    const task = async () => {
      try {
        await next();
      } catch (err) {
        await handleError(err, ctx);
      }
    };
    if (options.detach) {
      void queue.run(key, task);
      return;
    }
    await queue.run(key, task);
  });

  // 2. Захист від повторної обробки одного й того самого оновлення Telegram.
  bot.use(async (ctx, next) => {
    const fresh = await services.dedup.markProcessed(ctx.botInfo.id, ctx.update.update_id);
    if (!fresh) {
      logger.info({ updateId: ctx.update.update_id }, "Повторне оновлення Telegram пропущено");
      return;
    }
    return next();
  });

  // 3. Покупець заблокував/розблокував бота.
  bot.on("my_chat_member", async (ctx) => {
    const update = ctx.myChatMember;
    if (update.chat.type !== "private") return;
    const blocked = update.new_chat_member.status === "kicked";
    await services.customers.markBlockedByTelegramId(BigInt(update.from.id), blocked);
  });

  // 4. Магазин працює лише в особистих чатах.
  bot.use(async (ctx, next) => {
    if (!ctx.from || ctx.from.is_bot) return;
    if (ctx.chat && ctx.chat.type !== "private") return;
    ctx.customer = await services.customers.upsertFromTelegram(ctx.from);
    ctx.isAdmin = adminIds.has(String(ctx.from.id));
    return next();
  });

  // 5. Команди й кнопки
  registerStartHandlers(bot);
  registerAdminHandlers(bot);
  registerCatalogHandlers(bot);
  registerCheckoutHandlers(bot);

  // 6. Фото: використовуються лише в сценаріях адміністратора
  bot.on(message("photo"), async (ctx) => {
    const photos = ctx.message.photo;
    const largest = photos[photos.length - 1];
    if (ctx.isAdmin && largest && (await handleAdminPhoto(ctx, largest.file_id, ctx.message.caption))) return;
    if (ctx.message.caption) {
      await handleCustomerText(ctx, ctx.message.caption);
      return;
    }
    await ctx.reply("Дякую за фото! Напишіть, будь ласка, текстом, який набір LEGO ви шукаєте 🙂");
  });

  // 7. Текст: сцена адміністратора → оформлення замовлення → розмова (ШІ або резервний розбір)
  bot.on(message("text"), async (ctx) => {
    const text = ctx.message.text.trim();
    if (!text) return;
    if (text.startsWith("/")) {
      await ctx.reply("Невідома команда. Список команд — /help", { reply_markup: mainMenu(ctx.isAdmin).reply_markup });
      return;
    }
    if (ctx.isAdmin && (await handleAdminText(ctx, text))) return;
    await handleCustomerText(ctx, text);
  });

  // 8. Інші типи повідомлень (стікери, голосові тощо)
  bot.on("message", async (ctx) => {
    await ctx.reply("Я розумію текстові повідомлення 🙂 Напишіть, будь ласка, який набір LEGO ви шукаєте.");
  });

  bot.catch(async (err, ctx) => handleError(err, ctx));
  return { bot, queue };
}

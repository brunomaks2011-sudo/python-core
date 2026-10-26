import { TelegramError } from "telegraf";
import type { InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup } from "telegraf/types";
import { VERIFIED_NOTE, productCard, productListLines } from "../catalog/productPresenter.js";
import type { ProductView } from "../catalog/productService.js";
import { TELEGRAM_CAPTION_LIMIT, formatMoney, truncate } from "../lib/format.js";
import { logger } from "../lib/logger.js";
import { cb, type ListQuery } from "./callbackData.js";
import type { BotContext } from "./context.js";
import { btn } from "./keyboards.js";

type Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup;

export const HTML = { parse_mode: "HTML" as const, link_preview_options: { is_disabled: true } };

export function isNotModifiedError(err: unknown): boolean {
  return err instanceof TelegramError && /message is not modified/i.test(err.description);
}

/** Відповідь на натискання кнопки; помилки (застарілий запит) ігноруються. */
export async function answerCb(ctx: BotContext, text?: string, alert = false): Promise<void> {
  if (!ctx.callbackQuery) return;
  try {
    await ctx.answerCbQuery(text, { show_alert: alert });
  } catch {
    /* запит застарів — не критично */
  }
}

export async function reply(ctx: BotContext, text: string, markup?: Markup): Promise<void> {
  await ctx.reply(text, { ...HTML, ...(markup ? { reply_markup: markup } : {}) });
}

/** Редагує повідомлення з кнопкою (навігація каталогом) або надсилає нове. */
export async function replyOrEdit(ctx: BotContext, text: string, markup?: InlineKeyboardMarkup): Promise<void> {
  const message = ctx.callbackQuery?.message;
  if (message && "text" in message) {
    try {
      await ctx.editMessageText(text, { ...HTML, ...(markup ? { reply_markup: markup } : {}) });
      return;
    } catch (err) {
      if (isNotModifiedError(err)) return;
      logger.debug({ err }, "Не вдалося відредагувати повідомлення — надсилаємо нове");
    }
  }
  await reply(ctx, text, markup);
}

/** Прибирає кнопки з повідомлення, на якому натиснули кнопку. */
export async function clearButtons(ctx: BotContext): Promise<void> {
  if (!ctx.callbackQuery?.message) return;
  try {
    await ctx.editMessageReplyMarkup(undefined);
  } catch {
    /* повідомлення могло бути видалене або вже без кнопок */
  }
}

export function productCardButtons(p: ProductView): InlineKeyboardButton[][] {
  const rows: InlineKeyboardButton[][] = [];
  if (p.available > 0) rows.push([btn.callback("🛒 Замовити", cb.buy(p.id))]);
  rows.push([btn.callback("🧩 Схожі набори", cb.similar(p.id)), btn.callback("🧱 Каталог", cb.catalog())]);
  return rows;
}

/** Картка товару з фото (якщо є). Дані — лише з бази. */
export async function sendProductCard(
  ctx: BotContext,
  p: ProductView,
  opts: { intro?: string; footer?: string } = {},
): Promise<void> {
  const contact = ctx.services.config.shop.contact;
  const build = (descriptionLimit: number) =>
    [opts.intro, productCard(p, { contact, descriptionLimit }), opts.footer].filter(Boolean).join("\n\n");
  const markup = { inline_keyboard: productCardButtons(p) };
  const photo = p.telegramFileId ?? p.imageUrl;
  if (photo) {
    let caption = build(600);
    if (caption.length > TELEGRAM_CAPTION_LIMIT) caption = build(150);
    if (caption.length <= TELEGRAM_CAPTION_LIMIT) {
      try {
        await ctx.replyWithPhoto(photo, { caption, parse_mode: "HTML", reply_markup: markup });
        return;
      } catch (err) {
        logger.warn({ err, productId: p.id }, "Не вдалося надіслати фото товару — надсилаємо текстом");
      }
    }
  }
  await reply(ctx, build(1500), markup);
}

export const LIST_PAGE_SIZE = 8;

/** Компактний підпис кнопки: «1. 42151 Bugatti Bolide — 1 800 грн». */
export function productButtonLabel(p: ProductView, index?: number): string {
  const name = `${p.setNumber ? `${p.setNumber} ` : ""}${p.name}`;
  return `${index !== undefined ? `${index}. ` : ""}${truncate(name, 32)} — ${formatMoney(p.price)}`;
}

/** Список товарів з кнопками «деталі» та пагінацією. */
export function productListMessage(
  items: ProductView[],
  opts: { header: string; startIndex?: number; query?: ListQuery; total?: number; footer?: string },
): { text: string; markup: InlineKeyboardMarkup } {
  const start = opts.startIndex ?? 1;
  const lines = [opts.header, "", ...productListLines(items, start), "", VERIFIED_NOTE];
  lines.push(opts.footer ?? "Натисніть на набір, щоб переглянути деталі та замовити.");
  const rows: InlineKeyboardButton[][] = items.map((p, i) => [
    btn.callback(productButtonLabel(p, start + i), cb.product(p.id)),
  ]);
  if (opts.query && opts.total !== undefined) {
    const pages = Math.max(1, Math.ceil(opts.total / LIST_PAGE_SIZE));
    const page = opts.query.page;
    if (pages > 1) {
      const nav: InlineKeyboardButton[] = [];
      if (page > 1) nav.push(btn.callback("⬅️ Назад", cb.list({ ...opts.query, page: page - 1 })));
      nav.push(btn.callback(`${page}/${pages}`, cb.list({ ...opts.query, page })));
      if (page < pages) nav.push(btn.callback("Далі ➡️", cb.list({ ...opts.query, page: page + 1 })));
      rows.push(nav);
    }
  }
  rows.push([btn.callback("🧱 Каталог", cb.catalog())]);
  return { text: lines.join("\n"), markup: { inline_keyboard: rows } };
}

/** Показує «друкує…», поки виконується довга операція (запит до Claude). */
export async function withTyping<T>(ctx: BotContext, fn: () => Promise<T>): Promise<T> {
  const send = () => ctx.sendChatAction("typing").catch(() => undefined);
  void send();
  const timer = setInterval(send, 4500);
  try {
    return await fn();
  } finally {
    clearInterval(timer);
  }
}

export function customerName(ctx: BotContext): string {
  return ctx.customer.firstName ?? ctx.from?.first_name ?? "";
}

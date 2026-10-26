import type { Telegraf } from "telegraf";
import { escapeHtml, formatMoney } from "../../lib/format.js";
import { customerOrderDetailsText, orderShortLine } from "../../orders/orderPresenter.js";
import { cb } from "../callbackData.js";
import type { BotContext } from "../context.js";
import { MENU, btn, mainMenu } from "../keyboards.js";
import { HTML, answerCb, customerName, reply } from "../ui.js";
import { cancelCheckout } from "./checkout.js";
import { rememberShown, showProductDetails } from "./catalog.js";

export function helpText(ctx: BotContext): string {
  const shop = ctx.services.config.shop;
  return [
    `ℹ️ <b>Як користуватися ботом «${escapeHtml(shop.name)}»</b>`,
    "",
    "Пишіть звичайними словами, наприклад:",
    "• «Чи є LEGO Technic?»",
    "• «Покажи набори LEGO до 2000 грн»",
    "• «Шукаю набір LEGO 42151»",
    "• «Які набори є для дітей від 8 років?»",
    "• «Хочу замовити два набори»",
    "",
    "Команди:",
    "/catalog — каталог наборів",
    "/myorders — мої замовлення",
    "/cancel — скасувати оформлення замовлення",
    "/contact — зв’язатися з продавцем",
    "/privacy — які дані ми зберігаємо",
    "/unsubscribe — відписатися від розсилок",
    "",
    "Ціни та наявність бот бере лише з актуального каталогу магазину.",
  ].join("\n");
}

/** Привітання; постійному покупцю нагадуємо про попередню покупку, але не нав’язуємо повтор. */
export async function sendGreeting(ctx: BotContext, opts: { withMenu: boolean }): Promise<void> {
  const s = ctx.services;
  const name = customerName(ctx);
  const hello = `Вітаю${name ? `, ${escapeHtml(name)}` : ""}! 👋`;
  const purchased = await s.customers.purchasedSets(ctx.customer.id, 1);
  const last = purchased[0];

  if (opts.withMenu) {
    const intro = last
      ? `${hello} Раді бачити вас знову в магазині «${escapeHtml(s.config.shop.name)}».`
      : [
          `${hello} Це бот магазину «${escapeHtml(s.config.shop.name)}».`,
          "",
          "Я допоможу знайти набір LEGO, перевірити ціну та наявність і оформити замовлення.",
          "Просто напишіть, що шукаєте — наприклад, «Є LEGO Technic?» або «Набори до 2000 грн», — чи скористайтеся кнопками нижче.",
        ].join("\n");
    await ctx.reply(intro, { ...HTML, reply_markup: mainMenu(ctx.isAdmin).reply_markup });
  }

  if (last) {
    const text = `${opts.withMenu ? "" : `${hello}\n`}Раніше ви замовляли ${escapeHtml(last.title)}. Бажаєте перевірити актуальну наявність цього набору або подивитися схожі моделі?`;
    await reply(ctx, text, {
      inline_keyboard: [
        [btn.callback("🔄 Перевірити наявність", cb.product(last.productId))],
        [btn.callback("🧩 Схожі моделі", cb.similar(last.productId)), btn.callback("🧱 Каталог", cb.catalog())],
      ],
    });
    await rememberShown(ctx, `Нагадування про попередню покупку: ${last.title}`, [last.productId]);
  } else if (!opts.withMenu) {
    await reply(ctx, `${hello} Чим можу допомогти? Напишіть, який набір LEGO шукаєте, або відкрийте каталог.`, {
      inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]],
    });
  }
}

async function showMyOrders(ctx: BotContext): Promise<void> {
  const s = ctx.services;
  const orders = await s.orders.customerOrders(ctx.customer.id, 10);
  if (orders.length === 0) {
    await reply(ctx, "У вас ще немає замовлень. Перегляньте каталог — там багато цікавого 🧱", {
      inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]],
    });
    return;
  }
  const tz = s.config.shop.timezone;
  const lines = ["📦 <b>Ваші замовлення</b>", "", ...orders.map((o) => orderShortLine(o, tz))];
  const total = ctx.customer.totalSpent;
  if (Number(total) > 0) lines.push("", `Сума завершених покупок: <b>${formatMoney(total)}</b>`);
  await reply(ctx, lines.join("\n"), {
    inline_keyboard: orders.slice(0, 8).map((o) => [btn.callback(`Замовлення №${o.id}`, cb.myOrder(o.id))]),
  });
}

async function showMyOrder(ctx: BotContext, orderId: number): Promise<void> {
  const s = ctx.services;
  const order = await s.orders.getOrderForCustomer(orderId, ctx.customer.id);
  if (!order) {
    await reply(ctx, "Замовлення не знайдено.");
    return;
  }
  const productId = order.items[0]?.productId;
  await reply(ctx, customerOrderDetailsText(order, s.config.shop.timezone), {
    inline_keyboard: [
      ...(productId ? [[btn.callback("🔄 Перевірити наявність набору", cb.product(productId))]] : []),
      [btn.callback("⬅️ Усі замовлення", cb.myOrders())],
    ],
  });
}

async function showContact(ctx: BotContext): Promise<void> {
  const shop = ctx.services.config.shop;
  await reply(
    ctx,
    [
      `📞 <b>Зв’язок із продавцем</b>`,
      shop.contact ? escapeHtml(shop.contact) : "Напишіть своє запитання тут — менеджер магазину побачить замовлення та зв’яжеться з вами.",
      "",
      escapeHtml(shop.workingHours),
    ].join("\n"),
  );
}

async function showPrivacy(ctx: BotContext): Promise<void> {
  const days = ctx.services.config.retention.chatHistoryDays;
  await reply(
    ctx,
    [
      "🔐 <b>Які дані ми зберігаємо</b>",
      "",
      "• Telegram ID та ім’я користувача — щоб відповідати вам і пам’ятати ваші покупки.",
      "• Ім’я, телефон, місто та відділення — лише якщо ви вказали їх під час оформлення замовлення; вони потрібні для доставки.",
      "• Історію замовлень — для обліку й підтримки.",
      `• Останні повідомлення боту — до ${days} днів, щоб розуміти контекст розмови.`,
      "",
      "Дані не передаються іншим покупцям. Для розуміння текстових повідомлень можуть використовуватися сервіси штучного інтелекту (Claude API).",
      "",
      "Команди:",
      "/unsubscribe — не отримувати розсилки",
      "/forgetme — видалити ваші персональні дані",
    ].join("\n"),
  );
}

export function registerStartHandlers(bot: Telegraf<BotContext>): void {
  bot.start(async (ctx) => {
    const payload = ctx.payload?.trim();
    await sendGreeting(ctx, { withMenu: true });
    // Глибоке посилання t.me/<бот>?start=p_<id> відкриває картку товару
    const m = payload ? /^p_(\d+)$/.exec(payload) : null;
    if (m?.[1]) await showProductDetails(ctx, Number(m[1]));
  });

  bot.help(async (ctx) => reply(ctx, helpText(ctx)));
  bot.hears(MENU.help, async (ctx) => reply(ctx, helpText(ctx)));
  bot.action("nav:help", async (ctx) => {
    await answerCb(ctx);
    await reply(ctx, helpText(ctx));
  });

  bot.command("myorders", showMyOrders);
  bot.hears(MENU.myOrders, showMyOrders);
  bot.action("mo", async (ctx) => {
    await answerCb(ctx);
    await showMyOrders(ctx);
  });
  bot.action(/^mo:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    await showMyOrder(ctx, Number(ctx.match[1]));
  });

  bot.command("contact", showContact);
  bot.hears(MENU.contact, showContact);
  bot.command("privacy", showPrivacy);

  bot.command("unsubscribe", async (ctx) => {
    await ctx.services.customers.setMarketingOptOut(ctx.customer.id, true);
    await reply(ctx, "Готово: ви більше не отримуватимете розсилок. Повідомлення про ваші замовлення надходитимуть як і раніше. Повернути підписку — /subscribe");
  });
  bot.command("subscribe", async (ctx) => {
    await ctx.services.customers.setMarketingOptOut(ctx.customer.id, false);
    await reply(ctx, "Дякуємо! Ви знову отримуватимете новини магазину. Відписатися — /unsubscribe");
  });

  bot.command("forgetme", async (ctx) => {
    await reply(
      ctx,
      "⚠️ Видалити ваші персональні дані (ім’я, телефон, адресу доставки, історію повідомлень)?\nЗамовлення залишаться в обліку магазину, але без ваших контактних даних. Цю дію не можна скасувати.",
      {
        inline_keyboard: [
          [btn.callback("🗑 Так, видалити", cb.forgetMe(true)), btn.callback("Ні, залишити", cb.forgetMe(false))],
        ],
      },
    );
  });
  bot.action(/^pv:forget:([yn])$/, async (ctx) => {
    await answerCb(ctx);
    await ctx.editMessageReplyMarkup(undefined).catch(() => undefined);
    if (ctx.match[1] !== "y") {
      await reply(ctx, "Добре, дані залишаються без змін.");
      return;
    }
    const result = await ctx.services.customers.forget(ctx.customer.id);
    if (!result.ok) {
      await reply(
        ctx,
        `Зараз видалити дані неможливо: у вас є незавершені замовлення (${result.activeOrderIds
          .map((id) => `№${id}`)
          .join(", ")}). Дані потрібні для доставки — після завершення замовлень ви зможете їх видалити.`,
      );
      return;
    }
    await reply(ctx, "✅ Ваші персональні дані видалено. Дякуємо, що були з нами!");
  });

  bot.command("cancel", async (ctx) => {
    const telegramId = BigInt(ctx.from.id);
    const state = await ctx.services.userState.get(telegramId);
    if (state.scene) {
      await ctx.services.userState.clear(telegramId);
      await ctx.reply("Дію скасовано.", { reply_markup: mainMenu(ctx.isAdmin).reply_markup });
      return;
    }
    await cancelCheckout(ctx);
  });
}

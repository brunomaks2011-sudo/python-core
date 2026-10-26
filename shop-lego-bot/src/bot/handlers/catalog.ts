import type { Telegraf } from "telegraf";
import type { InlineKeyboardButton } from "telegraf/types";
import { productTitle } from "../../catalog/productPresenter.js";
import type { ProductView, SearchFilters } from "../../catalog/productService.js";
import { themeKey } from "../../catalog/themes.js";
import { escapeHtml, formatMoney } from "../../lib/format.js";
import { cb, parseListQuery, type ListQuery } from "../callbackData.js";
import type { BotContext } from "../context.js";
import { MENU, btn, chunk } from "../keyboards.js";
import {
  LIST_PAGE_SIZE,
  answerCb,
  productListMessage,
  reply,
  replyOrEdit,
  sendProductCard,
} from "../ui.js";

/** Запам'ятовує показані товари, щоб розуміти «цей набір» у наступних повідомленнях. */
export async function rememberShown(ctx: BotContext, text: string, productIds: number[]): Promise<void> {
  await ctx.services.chat.add(ctx.customer.id, "ASSISTANT", text, productIds);
}

export async function showCatalog(ctx: BotContext): Promise<void> {
  const themes = (await ctx.services.products.listThemes()).filter((t) => t.availableCount > 0);
  if (themes.length === 0) {
    const contact = ctx.services.config.shop.contact;
    await replyOrEdit(
      ctx,
      `На жаль, зараз у каталозі немає наборів у наявності 😔${
        contact ? `\nУточнити надходження можна в продавця: ${escapeHtml(contact)}` : ""
      }`,
    );
    return;
  }
  const themeButtons = themes.map((t) =>
    btn.callback(`${t.theme} (${t.availableCount})`, cb.list({ themeKey: themeKey(t.theme), page: 1 })),
  );
  const rows: InlineKeyboardButton[][] = [
    ...chunk(themeButtons, 2),
    [btn.callback("💰 За ціною", cb.catalogPrice()), btn.callback("👶 За віком", cb.catalogAge())],
    [btn.callback("📋 Усі набори в наявності", cb.list({ page: 1 }))],
  ];
  const total = themes.reduce((sum, t) => sum + t.availableCount, 0);
  await replyOrEdit(
    ctx,
    `🧱 <b>Каталог</b>\nУ наявності ${total} ${total === 1 ? "позиція" : total < 5 ? "позиції" : "позицій"}. Оберіть тематику або фільтр:`,
    { inline_keyboard: rows },
  );
}

const PRICE_BUCKETS: Array<{ label: string; min?: number; max?: number }> = [
  { label: "до 500 грн", max: 500 },
  { label: "до 1000 грн", max: 1000 },
  { label: "до 2000 грн", max: 2000 },
  { label: "до 3000 грн", max: 3000 },
  { label: "до 5000 грн", max: 5000 },
  { label: "від 5000 грн", min: 5000 },
];

const AGE_BUCKETS = [4, 6, 8, 10, 12, 18];

async function showPriceMenu(ctx: BotContext): Promise<void> {
  const rows = chunk(
    PRICE_BUCKETS.map((b) => btn.callback(b.label, cb.list({ minPrice: b.min, maxPrice: b.max, page: 1 }))),
    2,
  );
  rows.push([btn.callback("⬅️ До каталогу", cb.catalog())]);
  await replyOrEdit(ctx, "💰 Оберіть бюджет:", { inline_keyboard: rows });
}

async function showAgeMenu(ctx: BotContext): Promise<void> {
  const rows = chunk(
    AGE_BUCKETS.map((age) => btn.callback(age === 18 ? "Дорослим (18+)" : `Дитині ${age} років`, cb.list({ age, page: 1 }))),
    2,
  );
  rows.push([btn.callback("⬅️ До каталогу", cb.catalog())]);
  await replyOrEdit(ctx, "👶 Для кого обираєте набір? Покажу набори з відповідним рекомендованим віком:", {
    inline_keyboard: rows,
  });
}

/** Заголовок списку за фільтрами: «Набори LEGO Technic до 2000 грн». */
export function describeFilters(f: { theme?: string | null; minPrice?: number | null; maxPrice?: number | null; childAge?: number | null; condition?: string | null }): string {
  const parts: string[] = [];
  parts.push(f.theme ? `Набори ${f.theme}` : "Набори");
  if (f.condition === "USED") parts.push("(вживані)");
  if (f.minPrice != null && f.maxPrice != null) parts.push(`від ${formatMoney(f.minPrice)} до ${formatMoney(f.maxPrice)}`);
  else if (f.maxPrice != null) parts.push(`до ${formatMoney(f.maxPrice)}`);
  else if (f.minPrice != null) parts.push(`від ${formatMoney(f.minPrice)}`);
  if (f.childAge != null) parts.push(f.childAge >= 18 ? "для дорослих" : `для дитини ${f.childAge} років`);
  return parts.join(" ");
}

async function showList(ctx: BotContext, query: ListQuery): Promise<void> {
  const products = ctx.services.products;
  let themeName: string | null = null;
  if (query.themeKey) {
    const themes = await products.listThemes();
    themeName = themes.find((t) => themeKey(t.theme) === query.themeKey)?.theme ?? null;
    if (!themeName) {
      await replyOrEdit(ctx, "Ця тематика вже недоступна. Відкрийте каталог ще раз.", {
        inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]],
      });
      return;
    }
  }
  const filters: SearchFilters = {
    themeExact: themeName,
    minPrice: query.minPrice ?? null,
    maxPrice: query.maxPrice ?? null,
    childAge: query.age ?? null,
    condition: query.condition === "u" ? "USED" : query.condition === "n" ? "NEW" : null,
    sort: query.maxPrice || query.minPrice ? "price_asc" : "theme",
    limit: LIST_PAGE_SIZE,
    offset: (query.page - 1) * LIST_PAGE_SIZE,
  };
  const result = await products.search(filters);
  const header = `🧱 <b>${escapeHtml(
    describeFilters({ theme: themeName, minPrice: query.minPrice, maxPrice: query.maxPrice, childAge: query.age }),
  )}</b> — у наявності ${result.total}:`;
  if (result.items.length === 0) {
    await replyOrEdit(ctx, "На жаль, за цим фільтром зараз немає наборів у наявності.", {
      inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]],
    });
    return;
  }
  const { text, markup } = productListMessage(result.items, {
    header,
    startIndex: (query.page - 1) * LIST_PAGE_SIZE + 1,
    query,
    total: result.total,
  });
  await replyOrEdit(ctx, text, markup);
  await rememberShown(ctx, header.replace(/<[^>]+>/g, ""), result.items.map((p) => p.id));
}

export async function showProductDetails(ctx: BotContext, productId: number, intro?: string): Promise<void> {
  const p = await ctx.services.products.getById(productId);
  if (!p || p.status !== "ACTIVE") {
    await reply(ctx, "На жаль, цього товару вже немає в каталозі.", {
      inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]],
    });
    return;
  }
  await sendProductCard(ctx, p, {
    intro,
    footer: p.available > 0 ? "Бажаєте оформити замовлення?" : "Можу запропонувати схожі набори, які є в наявності.",
  });
  const introText = intro ? intro.replace(/<[^>]+>/g, "").trim() : "";
  await rememberShown(ctx, introText ? `${introText} [картка: ${productTitle(p)}]` : `Картка товару: ${productTitle(p)}`, [p.id]);
}

export async function showSimilar(ctx: BotContext, productId: number, header?: string): Promise<void> {
  const products = ctx.services.products;
  const base = await products.getById(productId);
  if (!base) {
    await showCatalog(ctx);
    return;
  }
  const similar = await products.findSimilar(base, 6);
  if (similar.length === 0) {
    await reply(ctx, "На жаль, схожих наборів зараз немає в наявності.", {
      inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]],
    });
    return;
  }
  const title = header ?? `🧩 Схожі набори, які є в наявності (до ${escapeHtml(productTitle(base))}):`;
  const { text, markup } = productListMessage(similar, { header: title });
  await reply(ctx, text, markup);
  await rememberShown(ctx, title.replace(/<[^>]+>/g, ""), similar.map((p) => p.id));
}

/** Список кількох товарів (наприклад, результат пошуку) або картка, якщо товар один. */
export async function showProducts(
  ctx: BotContext,
  items: ProductView[],
  opts: { header: string; singleIntro?: string; footer?: string },
): Promise<void> {
  if (items.length === 1) {
    await showProductDetails(ctx, items[0]!.id, opts.singleIntro ?? opts.header);
    return;
  }
  const { text, markup } = productListMessage(items, { header: opts.header, footer: opts.footer });
  await reply(ctx, text, markup);
  await rememberShown(ctx, opts.header.replace(/<[^>]+>/g, ""), items.map((p) => p.id));
}

/** Перевірка наявності конкретних наборів за номером. */
export async function lookupSetNumbers(ctx: BotContext, setNumbers: string[], greeting = ""): Promise<void> {
  const products = ctx.services.products;
  for (const number of setNumbers.slice(0, 3)) {
    const found = await products.findBySetNumber(number);
    const available = found.filter((p) => p.available > 0);
    if (found.length === 0) {
      const contact = ctx.services.config.shop.contact;
      await reply(
        ctx,
        `${greeting}На жаль, набору LEGO ${escapeHtml(number)} немає в каталозі нашого магазину.${
          contact ? `\nМожете уточнити можливість замовлення в продавця: ${escapeHtml(contact)}` : ""
        }`,
        { inline_keyboard: [[btn.callback("🧱 Переглянути каталог", cb.catalog())]] },
      );
      await rememberShown(ctx, `Набору ${number} немає в каталозі`, []);
      continue;
    }
    if (available.length === 0) {
      const first = found[0]!;
      await reply(
        ctx,
        `${greeting}На жаль, ${escapeHtml(productTitle(first))} зараз немає в наявності.\n\nМожу запропонувати інші набори, які є в магазині 👇`,
      );
      await rememberShown(ctx, `${productTitle(first)} немає в наявності`, [first.id]);
      await showSimilar(ctx, first.id, `🧩 Схожі набори в наявності:`);
      continue;
    }
    if (available.length === 1) {
      const p = available[0]!;
      await showProductDetails(ctx, p.id, `${greeting}Так, <b>${escapeHtml(productTitle(p))}</b> є в наявності! ✅`);
      continue;
    }
    await showProducts(ctx, available, {
      header: `${greeting}Набір ${escapeHtml(number)} є в наявності в кількох варіантах:`,
    });
  }
}

async function showSearchHint(ctx: BotContext): Promise<void> {
  await reply(
    ctx,
    "🔎 Напишіть, що шукаєте: назву чи номер набору, тематику або бюджет.\nНаприклад: <i>42151</i>, <i>Bugatti</i>, <i>LEGO City до 2000 грн</i>, <i>набори для дитини 8 років</i>.",
    { inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]] },
  );
}

export function registerCatalogHandlers(bot: Telegraf<BotContext>): void {
  bot.command("catalog", showCatalog);
  bot.hears(MENU.catalog, showCatalog);
  bot.command("search", showSearchHint);
  bot.hears(MENU.search, showSearchHint);

  bot.action("cat", async (ctx) => {
    await answerCb(ctx);
    await showCatalog(ctx);
  });
  bot.action("cat:price", async (ctx) => {
    await answerCb(ctx);
    await showPriceMenu(ctx);
  });
  bot.action("cat:age", async (ctx) => {
    await answerCb(ctx);
    await showAgeMenu(ctx);
  });
  bot.action(/^ls:(.+)$/, async (ctx) => {
    await answerCb(ctx);
    await showList(ctx, parseListQuery(ctx.match[1]!.split(":")));
  });
  bot.action(/^pr:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    await showProductDetails(ctx, Number(ctx.match[1]));
  });
  bot.action(/^sim:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    await showSimilar(ctx, Number(ctx.match[1]));
  });
}

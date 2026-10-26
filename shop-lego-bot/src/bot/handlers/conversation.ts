import type { Checkout } from "../../generated/prisma/client.js";
import type { AssistantReply } from "../../ai/assistant.js";
import { parseMessage, type Intent } from "../../ai/intentParser.js";
import { productTitle } from "../../catalog/productPresenter.js";
import type { ProductView } from "../../catalog/productService.js";
import { escapeHtml, formatMoney } from "../../lib/format.js";
import { logger } from "../../lib/logger.js";
import { looksLikeQuestion } from "../../lib/text.js";
import { PAYMENT_METHOD_LABELS } from "../../orders/orderStatus.js";
import { cb } from "../callbackData.js";
import type { BotContext } from "../context.js";
import { btn } from "../keyboards.js";
import { productListMessage, reply, withTyping } from "../ui.js";
import {
  describeFilters,
  lookupSetNumbers,
  rememberShown,
  showCatalog,
  showProductDetails,
  showProducts,
  showSimilar,
} from "./catalog.js";
import { handleCheckoutText, remindAboutCheckout, startCheckout } from "./checkout.js";
import { helpText, sendGreeting } from "./start.js";

const BARE_SET_NUMBER = /^\s*(?:lego|лего)?\s*[#№]?\s*(\d{3,7})(?:-\d)?\s*\??\s*$/iu;

/**
 * Головний обробник текстових повідомлень покупця:
 * 1) відповідь на крок оформлення замовлення;
 * 2) номер набору — точна перевірка в БД без ШІ;
 * 3) Claude AI (якщо ввімкнено) — розуміння довільного запиту;
 * 4) резервний розбір без ШІ.
 */
export async function handleCustomerText(ctx: BotContext, text: string): Promise<void> {
  const s = ctx.services;
  const checkout = await s.checkout.getActive(ctx.customer.id);
  if (checkout && !looksLikeQuestion(text)) {
    if (await handleCheckoutText(ctx, checkout, text)) return;
  }

  const [history, lastShownIds] = await Promise.all([
    s.chat.recent(ctx.customer.id, 8),
    s.chat.lastShownProductIds(ctx.customer.id),
  ]);
  await s.chat.add(ctx.customer.id, "USER", text);

  const bare = BARE_SET_NUMBER.exec(text);
  if (bare?.[1]) {
    await lookupSetNumbers(ctx, [bare[1]]);
    if (checkout) await remindAboutCheckout(ctx, checkout);
    return;
  }

  let answered = false;
  if (s.assistant && s.aiLimiter.tryAcquire(String(ctx.customer.id))) {
    try {
      const [lastShown, purchased] = await Promise.all([
        s.products.getMany(lastShownIds.slice(0, 8)),
        s.customers.purchasedSets(ctx.customer.id, 5),
      ]);
      const checkoutTitle = checkout?.productId
        ? await s.products.getById(checkout.productId).then((p) => (p ? productTitle(p) : null))
        : null;
      const assistant = s.assistant;
      const result = await withTyping(ctx, () =>
        s.aiSemaphore.use(() =>
          assistant.respond({
            customer: ctx.customer,
            text,
            history,
            lastShown,
            purchased,
            activeCheckoutTitle: checkout ? (checkoutTitle ?? "набір ще не обрано") : null,
          }),
        ),
      );
      if (result) {
        await renderAssistantReply(ctx, result);
        answered = true;
      }
    } catch (err) {
      logger.error({ err, customerId: ctx.customer.id }, "Помилка Claude API — використовуємо резервний розбір");
    }
  }
  if (!answered) {
    const parsed = parseMessage(text, { hasLastShown: lastShownIds.length > 0 });
    await handleIntent(ctx, parsed.intent, { greeting: parsed.greeting, lastShownIds, checkout });
  }

  if (checkout) {
    const stillActive = await s.checkout.getActive(ctx.customer.id);
    if (stillActive && stillActive.nonce === checkout.nonce) await remindAboutCheckout(ctx, stillActive);
  }
}

/** Відповідь ШІ: текст моделі + картки/список, сформовані кодом із БД. */
async function renderAssistantReply(ctx: BotContext, result: AssistantReply): Promise<void> {
  const s = ctx.services;
  const products = (await s.products.getMany(result.showProductIds)).filter((p) => p.status === "ACTIVE");
  const text = result.text ? escapeHtml(result.text) : "";
  if (products.length === 1) {
    // Картка сама записує показаний товар в історію діалогу
    await showProductDetails(ctx, products[0]!.id, text || undefined);
  } else {
    if (products.length > 1) {
      const { text: listText, markup } = productListMessage(products, { header: text || "Ось що є в каталозі:" });
      await reply(ctx, listText, markup);
    } else if (text) {
      await reply(ctx, text);
    }
    await s.chat.add(ctx.customer.id, "ASSISTANT", result.text ?? "", products.map((p) => p.id));
  }
  if (result.startCheckout) {
    await startCheckout(ctx, result.startCheckout);
  }
}

function shopInfoText(ctx: BotContext, topic: "delivery" | "payment" | "contacts" | "hours"): string {
  const shop = ctx.services.config.shop;
  switch (topic) {
    case "delivery":
      return `🚚 <b>Доставка</b>\n${escapeHtml(shop.deliveryInfo)}`;
    case "payment":
      return `💳 <b>Оплата</b>\n${escapeHtml(shop.paymentInfo)}\n\nДоступні способи: ${shop.paymentMethods
        .map((m) => PAYMENT_METHOD_LABELS[m])
        .join("; ")}.`;
    case "contacts":
      return `📞 <b>Контакти</b>\n${
        shop.contact ? escapeHtml(shop.contact) : "Напишіть запитання в цьому чаті — менеджер магазину відповість."
      }\n\n${escapeHtml(shop.workingHours)}`;
    case "hours":
      return `🕘 ${escapeHtml(shop.workingHours)}`;
  }
}

/** Виконання розпізнаного без ШІ наміру. Дані — лише з БД. */
export async function handleIntent(
  ctx: BotContext,
  intent: Intent,
  opts: { greeting: boolean; lastShownIds: number[]; checkout: Checkout | null },
): Promise<void> {
  const s = ctx.services;
  const hello = opts.greeting ? "Вітаю! 👋 " : "";
  switch (intent.type) {
    case "greeting_only":
      await sendGreeting(ctx, { withMenu: false });
      return;
    case "thanks":
      await reply(ctx, "Будь ласка! 😊 Якщо потрібно ще щось — просто напишіть.");
      return;
    case "help":
      await reply(ctx, helpText(ctx));
      return;
    case "catalog":
      if (hello) await reply(ctx, hello.trim());
      await showCatalog(ctx);
      return;
    case "my_orders": {
      const orders = await s.orders.customerOrders(ctx.customer.id, 5);
      if (orders.length === 0) {
        await reply(ctx, `${hello}У вас поки немає замовлень у нашому магазині. Допомогти обрати набір?`, {
          inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]],
        });
        return;
      }
      const purchased = await s.customers.purchasedSets(ctx.customer.id, 3);
      const last = purchased[0];
      await reply(
        ctx,
        `${hello}Так, бачу ваші замовлення 🙂${
          last ? `\nОстаннє: ${escapeHtml(last.title)} (замовлення №${last.lastOrderId}).` : ""
        }\nБажаєте перевірити наявність цього набору, подивитися схожі моделі чи статус замовлень?`,
        {
          inline_keyboard: [
            ...(last
              ? [[
                  btn.callback("🔄 Перевірити наявність", cb.product(last.productId)),
                  btn.callback("🧩 Схожі моделі", cb.similar(last.productId)),
                ]]
              : []),
            [btn.callback("📦 Мої замовлення", cb.myOrders())],
          ],
        },
      );
      if (last) await rememberShown(ctx, `Попередня покупка: ${last.title}`, [last.productId]);
      return;
    }
    case "shop_info":
      await reply(ctx, `${hello}${shopInfoText(ctx, intent.topic)}`);
      return;
    case "product_lookup":
      await lookupSetNumbers(ctx, intent.setNumbers, hello);
      return;
    case "order":
      await handleOrderIntent(ctx, intent, opts.lastShownIds);
      return;
    case "about_last_shown": {
      const shown = await s.products.getMany(opts.lastShownIds);
      if (shown.length === 0) {
        await reply(ctx, "Уточніть, будь ласка, про який набір ідеться — напишіть назву або номер.");
        return;
      }
      if (shown.length > 1) {
        const { text, markup } = productListMessage(shown.slice(0, 8), {
          header: "Уточніть, будь ласка, про який саме набір ідеться:",
        });
        await reply(ctx, text, markup);
        return;
      }
      const p = shown[0]!;
      if (intent.aspect === "similar") {
        await showSimilar(ctx, p.id);
        return;
      }
      const title = `<b>${escapeHtml(productTitle(p))}</b>`;
      const intro =
        intent.aspect === "price"
          ? `${title} коштує <b>${formatMoney(p.price)}</b>${p.available > 0 ? ` — є в наявності (${p.available} шт.).` : ", але зараз його немає в наявності."}`
          : p.available > 0
            ? `Так, ${title} є в наявності ✅`
            : `На жаль, ${title} зараз немає в наявності.`;
      await showProductDetails(ctx, p.id, intro);
      if (p.available === 0) await showSimilar(ctx, p.id, "🧩 Схожі набори, які є в наявності:");
      return;
    }
    case "search":
      await handleSearch(ctx, intent.filters, hello);
      return;
    case "unknown": {
      const contact = s.config.shop.contact;
      await reply(
        ctx,
        `${hello}Я не зовсім зрозумів запит 🤔\nНапишіть, будь ласка, назву чи номер набору, тематику (наприклад, «LEGO City») або бюджет («до 2000 грн»).${
          contact ? `\nТакож можна звернутися до продавця: ${escapeHtml(contact)}` : ""
        }`,
        { inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog()), btn.callback("ℹ️ Допомога", cb.help())]] },
      );
      return;
    }
  }
}

async function handleOrderIntent(
  ctx: BotContext,
  intent: Extract<Intent, { type: "order" }>,
  lastShownIds: number[],
): Promise<void> {
  const s = ctx.services;
  if (intent.setNumber) {
    const found = (await s.products.findBySetNumber(intent.setNumber)).filter((p) => p.available > 0);
    if (found.length === 1) {
      await startCheckout(ctx, { productId: found[0]!.id, quantity: intent.quantity });
      return;
    }
    if (found.length > 1) {
      await chooseForOrder(ctx, found, "Цей набір є в кількох варіантах. Оберіть, який замовити:");
      return;
    }
    await lookupSetNumbers(ctx, [intent.setNumber]);
    return;
  }
  const shown = (await s.products.getMany(lastShownIds)).filter((p) => p.available > 0);
  if (shown.length === 1) {
    await startCheckout(ctx, { productId: shown[0]!.id, quantity: intent.quantity });
    return;
  }
  if (shown.length > 1) {
    await chooseForOrder(ctx, shown, "Який саме набір бажаєте замовити?");
    return;
  }
  await startCheckout(ctx, { productId: null, quantity: intent.quantity });
}

async function chooseForOrder(ctx: BotContext, items: ProductView[], header: string): Promise<void> {
  const { text } = productListMessage(items.slice(0, 8), { header, footer: "Натисніть «Замовити» під потрібним набором." });
  await reply(ctx, text, {
    inline_keyboard: items.slice(0, 8).map((p, i) => [
      btn.callback(`🛒 ${i + 1}. ${productTitle(p).slice(0, 40)}`, cb.buy(p.id)),
    ]),
  });
  await rememberShown(ctx, header, items.map((p) => p.id));
}

async function handleSearch(
  ctx: BotContext,
  filters: Extract<Intent, { type: "search" }>["filters"],
  hello: string,
): Promise<void> {
  const s = ctx.services;
  const result = await s.products.search({
    text: filters.text,
    theme: filters.theme,
    minPrice: filters.minPrice,
    maxPrice: filters.maxPrice,
    childAge: filters.childAge,
    condition: filters.condition,
    sort: filters.maxPrice !== null || filters.minPrice !== null ? "price_asc" : "relevance",
    limit: 8,
  });
  const theme = filters.theme ?? result.detectedTheme;
  const description = describeFilters({ ...filters, theme });
  if (result.items.length > 0) {
    const onlyTheme = theme && !filters.text && filters.maxPrice === null && filters.minPrice === null && filters.childAge === null;
    const header = onlyTheme
      ? `${hello}Так, у нас є набори ${escapeHtml(theme)}! Ось варіанти:`
      : `${hello}${escapeHtml(description)}${filters.text ? ` за запитом «${escapeHtml(filters.text)}»` : ""} — у наявності:`;
    await showProducts(ctx, result.items, {
      header,
      singleIntro: onlyTheme ? `${hello}Так, у нас є набір ${escapeHtml(theme)}:` : `${hello}Знайшов такий набір у наявності:`,
      footer: result.total > result.items.length ? `Показано ${result.items.length} з ${result.total}. Уточніть запит або відкрийте каталог.` : undefined,
    });
    return;
  }
  // Нічого немає — пропонуємо лише те, що справді є в каталозі
  const attempts: Array<{ filters: Parameters<typeof s.products.search>[0]; header: string }> = [];
  if (theme && (filters.text || filters.childAge !== null || filters.condition)) {
    attempts.push({
      filters: { theme, maxPrice: filters.maxPrice, minPrice: filters.minPrice, sort: "price_asc", limit: 5 },
      header: `Інші набори ${escapeHtml(theme)} у наявності:`,
    });
  }
  if (theme && (filters.maxPrice !== null || filters.minPrice !== null)) {
    attempts.push({
      filters: { theme, sort: "price_asc", limit: 5 },
      header: `Набори ${escapeHtml(theme)}, які є в наявності (без обмеження ціни):`,
    });
  }
  if (filters.maxPrice !== null && !theme) {
    attempts.push({
      filters: { sort: "price_asc", limit: 5 },
      header: "Найдоступніші набори, які є в наявності:",
    });
  }
  attempts.push({ filters: { sort: "newest", limit: 5 }, header: "Можу запропонувати інші набори, які є в магазині:" });

  const onlyText =
    filters.text && !theme && filters.maxPrice === null && filters.minPrice === null && filters.childAge === null && !filters.condition;
  const noneText = onlyText
    ? `${hello}На жаль, за запитом «${escapeHtml(filters.text!)}» у каталозі нічого не знайшлося 🤔\nСпробуйте написати назву чи номер набору або тематику (наприклад, «LEGO City»).`
    : `${hello}На жаль, ${escapeHtml(description.replace(/^Набори/, "наборів"))}${
        filters.text ? ` за запитом «${escapeHtml(filters.text)}»` : ""
      } зараз немає в наявності.`;
  for (const attempt of attempts) {
    const alt = await s.products.search(attempt.filters);
    if (alt.items.length > 0) {
      await reply(ctx, noneText);
      await showProducts(ctx, alt.items, { header: attempt.header });
      return;
    }
  }
  await reply(ctx, `${noneText}\nНаразі в каталозі немає наборів у наявності — завітайте трохи згодом 🙏`);
}

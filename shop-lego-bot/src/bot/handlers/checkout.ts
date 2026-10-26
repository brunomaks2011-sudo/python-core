import { Markup, type Telegraf } from "telegraf";
import { message } from "telegraf/filters";
import type { InlineKeyboardButton } from "telegraf/types";
import type { Checkout, CheckoutStep, PaymentMethod } from "../../generated/prisma/client.js";
import { conditionText, productTitle } from "../../catalog/productPresenter.js";
import type { ProductView } from "../../catalog/productService.js";
import { escapeHtml, formatMoney, formatSets } from "../../lib/format.js";
import { logger } from "../../lib/logger.js";
import { extractSetNumbers, parseQuantity } from "../../lib/text.js";
import {
  normalizePhone,
  validateCity,
  validateDeliveryPoint,
  validateFullName,
  type ValidationResult,
} from "../../lib/validation.js";
import { nextCheckoutStep, type CheckoutPatch } from "../../orders/checkoutService.js";
import { customerOrderCreatedText } from "../../orders/orderPresenter.js";
import { PAYMENT_METHOD_BUTTONS, PAYMENT_METHOD_LABELS } from "../../orders/orderStatus.js";
import { cb, paymentFromCode, type CheckoutEditField } from "../callbackData.js";
import type { BotContext } from "../context.js";
import { btn, chunk, mainMenu } from "../keyboards.js";
import { HTML, answerCb, clearButtons, productButtonLabel, reply } from "../ui.js";
import { rememberShown, showSimilar } from "./catalog.js";

const cancelRow = (nonce: number): InlineKeyboardButton[] => [
  btn.callback("❌ Скасувати оформлення", cb.checkoutCancel(nonce)),
];

function shopTexts(ctx: BotContext) {
  const c = ctx.services.config.shop;
  return { contact: c.contact, paymentDetails: c.paymentDetails, timezone: c.timezone };
}

/** Починає оформлення замовлення (з карток, кнопок, тексту чи за рішенням ШІ). */
export async function startCheckout(
  ctx: BotContext,
  init: { productId?: number | null; quantity?: number | null } = {},
): Promise<void> {
  const s = ctx.services;
  let quantity = init.quantity ?? null;
  if (init.productId) {
    const p = await s.products.getById(init.productId);
    if (!p || p.status !== "ACTIVE") {
      await reply(ctx, "На жаль, цього набору вже немає в каталозі.", {
        inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]],
      });
      return;
    }
    if (p.available === 0) {
      await reply(ctx, `На жаль, ${escapeHtml(productTitle(p))} зараз немає в наявності 😔`);
      await showSimilar(ctx, p.id, "🧩 Можу запропонувати схожі набори, які є в наявності:");
      return;
    }
    const maxAllowed = Math.min(p.available, s.config.shop.maxQuantityPerOrder);
    if (quantity !== null && quantity > maxAllowed) {
      await reply(
        ctx,
        quantity > p.available
          ? `Зараз доступно лише ${p.available} шт. цього набору — оберіть, будь ласка, кількість у межах наявності.`
          : `В одному замовленні можна придбати до ${maxAllowed} шт. — оберіть, будь ласка, кількість.`,
      );
      quantity = null;
    }
  }
  const checkout = await s.checkout.start(ctx.customer.id, { productId: init.productId ?? null, quantity });
  await promptStep(ctx, checkout);
}

/** Надсилає запит наступного кроку. Крок визначається тим, яких даних ще бракує. */
export async function promptStep(ctx: BotContext, checkout: Checkout): Promise<void> {
  const s = ctx.services;
  const hasSavedProfile = s.customers.hasSavedProfile(ctx.customer);
  let step: CheckoutStep = checkout.editingField ?? nextCheckoutStep(checkout, { hasSavedProfile });
  if (step === "REUSE_PROFILE" && !hasSavedProfile) step = "FULL_NAME";
  if (checkout.step !== step) {
    const updated = await s.checkout.update(ctx.customer.id, checkout.nonce, { step });
    if (!updated) return;
    checkout = updated;
  }
  const nonce = checkout.nonce;

  switch (step) {
    case "PRODUCT": {
      await reply(
        ctx,
        "🛒 <b>Оформлення замовлення</b>\n\nЯкий набір ви хочете придбати? Напишіть назву або номер набору (наприклад: <i>42151</i>) чи оберіть у каталозі.",
        { inline_keyboard: [[btn.callback("🧱 Обрати в каталозі", cb.catalog())], cancelRow(nonce)] },
      );
      return;
    }
    case "QUANTITY": {
      const p = await s.products.getById(checkout.productId!);
      if (!p || p.available === 0) {
        await handleProductGone(ctx, checkout, p);
        return;
      }
      const max = Math.min(p.available, s.config.shop.maxQuantityPerOrder);
      const buttons = Array.from({ length: Math.min(max, 5) }, (_, i) =>
        btn.callback(String(i + 1), cb.checkoutQuantity(nonce, i + 1)),
      );
      await reply(
        ctx,
        `🛒 <b>${escapeHtml(productTitle(p))}</b>\nЦіна: <b>${formatMoney(p.price)}</b> · доступно: ${p.available} шт.\n\nСкільки наборів бажаєте замовити?${
          max > 5 ? ` Можна написати число до ${max}.` : ""
        }`,
        { inline_keyboard: [buttons, cancelRow(nonce)] },
      );
      return;
    }
    case "REUSE_PROFILE": {
      const c = ctx.customer;
      await reply(
        ctx,
        [
          "Використати дані з попереднього замовлення?",
          "",
          `👤 ${escapeHtml(c.fullName ?? "")}`,
          `📞 ${escapeHtml(c.phone ?? "")}`,
          `📍 ${escapeHtml(c.city ?? "")}, ${escapeHtml(c.deliveryPoint ?? "")}`,
        ].join("\n"),
        {
          inline_keyboard: [
            [
              btn.callback("✅ Так, використати", cb.checkoutReuse(nonce, true)),
              btn.callback("✏️ Ввести інші", cb.checkoutReuse(nonce, false)),
            ],
            cancelRow(nonce),
          ],
        },
      );
      return;
    }
    case "FULL_NAME":
      await reply(ctx, "👤 Вкажіть, будь ласка, <b>ім’я та прізвище</b> отримувача:", { inline_keyboard: [cancelRow(nonce)] });
      return;
    case "PHONE":
      await ctx.reply(
        "📞 Вкажіть <b>номер телефону</b> отримувача (наприклад: +380 67 123 45 67) або натисніть кнопку нижче, щоб надіслати свій номер.",
        {
          ...HTML,
          reply_markup: Markup.keyboard([[Markup.button.contactRequest("📱 Надіслати мій номер")], ["❌ Скасувати оформлення"]])
            .resize()
            .oneTime().reply_markup,
        },
      );
      return;
    case "CITY":
      await reply(ctx, "🏙 Вкажіть <b>місто</b> (населений пункт) доставки:", { inline_keyboard: [cancelRow(nonce)] });
      return;
    case "DELIVERY_POINT":
      await reply(ctx, `📮 ${escapeHtml(s.config.shop.deliveryHint)}`, { inline_keyboard: [cancelRow(nonce)] });
      return;
    case "PAYMENT": {
      const rows = s.config.shop.paymentMethods.map((m) => [
        btn.callback(PAYMENT_METHOD_BUTTONS[m], cb.checkoutPayment(nonce, m)),
      ]);
      await reply(ctx, "💳 Оберіть <b>спосіб оплати</b>:", { inline_keyboard: [...rows, cancelRow(nonce)] });
      return;
    }
    case "EDIT_MENU":
      await showEditMenu(ctx, checkout);
      return;
    case "SUMMARY":
      await showSummary(ctx, checkout);
      return;
  }
}

async function handleProductGone(ctx: BotContext, checkout: Checkout, p: ProductView | null): Promise<void> {
  await ctx.services.checkout.update(ctx.customer.id, checkout.nonce, {
    productId: null,
    quantity: null,
    step: "PRODUCT",
    editingField: null,
  });
  if (p) {
    await reply(ctx, `На жаль, ${escapeHtml(productTitle(p))} щойно закінчився 😔`);
    await showSimilar(ctx, p.id, "🧩 Можу запропонувати схожі набори в наявності — оберіть інший або скасуйте оформлення:");
  } else {
    await reply(ctx, "На жаль, цього набору вже немає в каталозі. Оберіть, будь ласка, інший.");
  }
  await reply(ctx, "Щоб продовжити, напишіть назву чи номер іншого набору або скасуйте оформлення.", {
    inline_keyboard: [cancelRow(checkout.nonce)],
  });
}

async function showSummary(ctx: BotContext, checkout: Checkout): Promise<void> {
  const s = ctx.services;
  const p = await s.products.getById(checkout.productId!);
  if (!p || p.available === 0) {
    await handleProductGone(ctx, checkout, p);
    return;
  }
  if (checkout.quantity! > p.available) {
    await s.checkout.update(ctx.customer.id, checkout.nonce, { quantity: null, editingField: null });
    await reply(ctx, `⚠️ Зараз доступно лише ${p.available} шт. цього набору. Оберіть, будь ласка, кількість ще раз.`);
    const refreshed = await s.checkout.getActive(ctx.customer.id);
    if (refreshed) await promptStep(ctx, refreshed);
    return;
  }
  const updated = await s.checkout.update(ctx.customer.id, checkout.nonce, {
    quotedUnitPrice: p.price,
    step: "SUMMARY",
    editingField: null,
  });
  if (!updated) return;
  const total = p.price.mul(updated.quantity!);
  const text = [
    "🧾 <b>Перевірте, будь ласка, замовлення</b>",
    "",
    `Набір: <b>${escapeHtml(productTitle(p))}</b>`,
    `Номер набору LEGO: ${p.setNumber ? escapeHtml(p.setNumber) : "<i>не вказано</i>"}`,
    `Стан: ${conditionText(p)}`,
    `Кількість: ${formatSets(updated.quantity!)}`,
    `Ціна за одиницю: ${formatMoney(p.price)}`,
    `<b>Загальна вартість: ${formatMoney(total)}</b>`,
    "",
    `👤 Отримувач: ${escapeHtml(updated.fullName!)}`,
    `📞 Телефон: ${escapeHtml(updated.phone!)}`,
    `📍 Доставка: ${escapeHtml(updated.city!)}, ${escapeHtml(updated.deliveryPoint!)}`,
    `💳 Оплата: ${PAYMENT_METHOD_LABELS[updated.paymentMethod!]}`,
    "",
    "Усе правильно?",
  ].join("\n");
  await reply(ctx, text, {
    inline_keyboard: [
      [btn.callback("✅ Підтвердити замовлення", cb.checkoutConfirm(updated.nonce))],
      [
        btn.callback("✏️ Змінити дані", cb.checkoutEdit(updated.nonce)),
        btn.callback("❌ Скасувати замовлення", cb.checkoutCancel(updated.nonce)),
      ],
    ],
  });
}

const EDIT_FIELDS: Array<{ field: CheckoutEditField; label: string }> = [
  { field: "PRODUCT", label: "🧱 Набір" },
  { field: "QUANTITY", label: "🔢 Кількість" },
  { field: "FULL_NAME", label: "👤 Ім’я та прізвище" },
  { field: "PHONE", label: "📞 Телефон" },
  { field: "CITY", label: "🏙 Місто" },
  { field: "DELIVERY_POINT", label: "📮 Відділення" },
  { field: "PAYMENT", label: "💳 Оплата" },
];

async function showEditMenu(ctx: BotContext, checkout: Checkout): Promise<void> {
  const rows = chunk(
    EDIT_FIELDS.map((f) => btn.callback(f.label, cb.checkoutEditField(checkout.nonce, f.field))),
    2,
  );
  rows.push([btn.callback("⬅️ Назад до підсумку", cb.checkoutSummary(checkout.nonce))]);
  await reply(ctx, "Що потрібно змінити?", { inline_keyboard: rows });
}

/** Зберігає поле, повертається до підсумку, якщо покупець редагував дані з нього. */
async function saveAndContinue(ctx: BotContext, checkout: Checkout, patch: CheckoutPatch): Promise<void> {
  const updated = await ctx.services.checkout.update(ctx.customer.id, checkout.nonce, { ...patch, editingField: null });
  if (!updated) {
    await reply(ctx, "Це оформлення вже неактуальне. Почніть, будь ласка, заново.");
    return;
  }
  await promptStep(ctx, updated);
}

function currentStep(checkout: Checkout): CheckoutStep {
  return checkout.editingField ?? checkout.step;
}

async function validationError(ctx: BotContext, checkout: Checkout, error: string): Promise<void> {
  await reply(ctx, `⚠️ ${escapeHtml(error)}`, { inline_keyboard: [cancelRow(checkout.nonce)] });
}

async function applyValidated<T>(
  ctx: BotContext,
  checkout: Checkout,
  result: ValidationResult<T>,
  toPatch: (value: T) => CheckoutPatch,
): Promise<void> {
  if (!result.ok) {
    await validationError(ctx, checkout, result.error);
    return;
  }
  await saveAndContinue(ctx, checkout, toPatch(result.value));
}

async function setQuantity(ctx: BotContext, checkout: Checkout, quantity: number): Promise<void> {
  const s = ctx.services;
  const p = checkout.productId ? await s.products.getById(checkout.productId) : null;
  if (!p || p.available === 0) {
    await handleProductGone(ctx, checkout, p);
    return;
  }
  const max = Math.min(p.available, s.config.shop.maxQuantityPerOrder);
  if (quantity < 1 || quantity > max) {
    await validationError(
      ctx,
      checkout,
      quantity > p.available
        ? `Зараз доступно лише ${p.available} шт. Вкажіть кількість від 1 до ${max}.`
        : `Вкажіть кількість від 1 до ${max}.`,
    );
    return;
  }
  await saveAndContinue(ctx, checkout, { quantity });
}

async function chooseProduct(ctx: BotContext, checkout: Checkout, productId: number): Promise<void> {
  const p = await ctx.services.products.getById(productId);
  if (!p || p.status !== "ACTIVE" || p.available === 0) {
    await reply(ctx, "На жаль, цього набору зараз немає в наявності. Оберіть, будь ласка, інший.");
    return;
  }
  // Кількість, яку покупець назвав до вибору набору («хочу два набори»), зберігаємо, якщо її вистачає.
  const max = Math.min(p.available, ctx.services.config.shop.maxQuantityPerOrder);
  const keepQuantity =
    checkout.productId === productId ||
    (checkout.productId === null && checkout.quantity !== null && checkout.quantity <= max);
  if (checkout.productId === null && checkout.quantity !== null && !keepQuantity) {
    await reply(ctx, `Зараз доступно ${p.available} шт. цього набору — оберіть, будь ласка, кількість.`);
  }
  await saveAndContinue(ctx, checkout, { productId, ...(keepQuantity ? {} : { quantity: null }) });
}

/** Обробляє текст, коли покупець перебуває на кроці оформлення. Повертає false, якщо текст не для оформлення. */
export async function handleCheckoutText(ctx: BotContext, checkout: Checkout, text: string): Promise<boolean> {
  const s = ctx.services;
  switch (currentStep(checkout)) {
    case "PRODUCT": {
      const numbers = extractSetNumbers(text);
      const candidates = numbers.length
        ? (await Promise.all(numbers.map((n) => s.products.findBySetNumber(n)))).flat()
        : (await s.products.search({ text, limit: 6 })).items;
      const available = candidates.filter((p) => p.available > 0);
      if (available.length === 1) {
        await chooseProduct(ctx, checkout, available[0]!.id);
      } else if (available.length > 1) {
        const rows: InlineKeyboardButton[][] = available.slice(0, 8).map((p) => [
          btn.callback(productButtonLabel(p), cb.checkoutPick(checkout.nonce, p.id)),
        ]);
        rows.push(cancelRow(checkout.nonce));
        await reply(ctx, "Знайшлося кілька наборів. Оберіть потрібний:", { inline_keyboard: rows });
        await rememberShown(ctx, "Вибір набору для замовлення", available.map((p) => p.id));
      } else {
        await reply(
          ctx,
          candidates.length > 0
            ? "На жаль, цього набору зараз немає в наявності. Напишіть інший набір або оберіть у каталозі."
            : "Не знайшов такого набору в каталозі. Спробуйте інший запит (назву або номер набору) чи оберіть у каталозі.",
          { inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())], cancelRow(checkout.nonce)] },
        );
      }
      return true;
    }
    case "QUANTITY": {
      const quantity = parseQuantity(text);
      if (quantity === null) {
        await validationError(ctx, checkout, "Вкажіть кількість числом, наприклад: 1");
        return true;
      }
      await setQuantity(ctx, checkout, quantity);
      return true;
    }
    case "REUSE_PROFILE": {
      const normalized = text.trim().toLowerCase();
      if (/^(так|да|yes|ок|ok|використати|використай|авжеж)/u.test(normalized)) {
        await reuseProfile(ctx, checkout, true);
      } else if (/^(ні|нет|no|інші|нові|ввести)/u.test(normalized)) {
        await reuseProfile(ctx, checkout, false);
      } else {
        await promptStep(ctx, checkout);
      }
      return true;
    }
    case "FULL_NAME":
      await applyValidated(ctx, checkout, validateFullName(text), (fullName) => ({ fullName }));
      return true;
    case "PHONE": {
      if (/скасувати оформлення/i.test(text)) {
        await cancelCheckout(ctx, checkout.nonce);
        return true;
      }
      const result = normalizePhone(text);
      if (result.ok) await ctx.reply("✅ Телефон збережено", { reply_markup: mainMenu(ctx.isAdmin).reply_markup });
      await applyValidated(ctx, checkout, result, (phone) => ({ phone }));
      return true;
    }
    case "CITY":
      await applyValidated(ctx, checkout, validateCity(text), (city) => ({ city }));
      return true;
    case "DELIVERY_POINT":
      await applyValidated(ctx, checkout, validateDeliveryPoint(text), (deliveryPoint) => ({ deliveryPoint }));
      return true;
    case "PAYMENT": {
      const lower = text.toLowerCase();
      const method = s.config.shop.paymentMethods.find((m) =>
        m === "CASH_ON_DELIVERY"
          ? /(наклад|при отриманні|готівк|на пошті)/u.test(lower)
          : m === "CARD_TRANSFER"
            ? /(карт|переказ)/u.test(lower)
            : /(реквізит|iban|рахун)/u.test(lower),
      );
      if (method) await saveAndContinue(ctx, checkout, { paymentMethod: method });
      else await promptStep(ctx, checkout);
      return true;
    }
    case "SUMMARY": {
      // Підтвердження — лише кнопкою; на «так» показуємо підсумок ще раз.
      if (/^(так|да|ок|ok|підтверджую|підтвердити|оформлюй|оформити|згоден|згодна|все вірно|все правильно)/u.test(text.trim().toLowerCase())) {
        await reply(ctx, "Щоб оформити замовлення, натисніть кнопку «✅ Підтвердити замовлення» під підсумком 👇");
        await showSummary(ctx, checkout);
        return true;
      }
      return false;
    }
    default:
      return false;
  }
}

async function reuseProfile(ctx: BotContext, checkout: Checkout, reuse: boolean): Promise<void> {
  const c = ctx.customer;
  await saveAndContinue(
    ctx,
    checkout,
    reuse
      ? { profileOffered: true, fullName: c.fullName, phone: c.phone, city: c.city, deliveryPoint: c.deliveryPoint }
      : { profileOffered: true },
  );
}

export async function cancelCheckout(ctx: BotContext, nonce?: number): Promise<void> {
  const cancelled = await ctx.services.checkout.cancel(ctx.customer.id, nonce);
  await ctx.reply(cancelled ? "Оформлення замовлення скасовано. Якщо передумаєте — я поруч 🙂" : "Немає активного оформлення.", {
    reply_markup: mainMenu(ctx.isAdmin).reply_markup,
  });
}

/** Нагадування про незавершене оформлення після відповіді на стороннє запитання. */
export async function remindAboutCheckout(ctx: BotContext, checkout: Checkout): Promise<void> {
  const p = checkout.productId ? await ctx.services.products.getById(checkout.productId) : null;
  await reply(
    ctx,
    `📝 У вас є незавершене оформлення замовлення${p ? `: ${escapeHtml(productTitle(p))}` : ""}.`,
    {
      inline_keyboard: [
        [
          btn.callback("▶️ Продовжити оформлення", cb.checkoutContinue()),
          btn.callback("❌ Скасувати", cb.checkoutCancel(checkout.nonce)),
        ],
      ],
    },
  );
}

async function confirmOrder(ctx: BotContext, nonce: number): Promise<void> {
  const s = ctx.services;
  const result = await s.orders.placeOrder({ customerId: ctx.customer.id, nonce });
  switch (result.kind) {
    case "created": {
      await clearButtons(ctx);
      // Одразу повідомляємо магазин; після успішного сповіщення статус стає «очікує підтвердження».
      try {
        await s.notifications.processDue({ orderId: result.order.id });
      } catch (err) {
        logger.error({ err, orderId: result.order.id }, "Не вдалося одразу надіслати сповіщення — повторить фоновий обробник");
      }
      const order = (await s.orders.getOrderForCustomer(result.order.id, ctx.customer.id)) ?? result.order;
      await ctx.reply(customerOrderCreatedText(order, shopTexts(ctx)), {
        ...HTML,
        reply_markup: mainMenu(ctx.isAdmin).reply_markup,
      });
      await s.chat.add(ctx.customer.id, "ASSISTANT", `Оформлено замовлення №${order.id}`, order.items.map((i) => i.productId));
      logger.info({ orderId: order.id, customerId: ctx.customer.id, total: order.totalAmount.toString() }, "Нове замовлення");
      return;
    }
    case "duplicate":
      await clearButtons(ctx);
      await reply(
        ctx,
        `Це замовлення вже оформлено: <b>№${result.order.id}</b>. Переглянути статус можна в розділі «📦 Мої замовлення».`,
      );
      return;
    case "stale":
      await clearButtons(ctx);
      await reply(ctx, "Ця кнопка вже неактуальна. Якщо бажаєте зробити замовлення — почніть оформлення заново.");
      return;
    case "incomplete": {
      const checkout = await s.checkout.getActive(ctx.customer.id);
      if (checkout) await promptStep(ctx, checkout);
      return;
    }
    case "unavailable": {
      const checkout = await s.checkout.getActive(ctx.customer.id);
      if (checkout) await handleProductGone(ctx, checkout, null);
      return;
    }
    case "price_changed": {
      await clearButtons(ctx);
      await reply(
        ctx,
        `⚠️ Ціна на цей набір щойно змінилася${
          result.oldPrice ? `: було ${formatMoney(result.oldPrice)}, стало ${formatMoney(result.newPrice)}` : ""
        }. Перевірте, будь ласка, підсумок ще раз.`,
      );
      const checkout = await s.checkout.getActive(ctx.customer.id);
      if (checkout) await showSummary(ctx, checkout);
      return;
    }
    case "insufficient_stock": {
      await clearButtons(ctx);
      const checkout = await s.checkout.getActive(ctx.customer.id);
      if (!checkout) return;
      if (result.available === 0) {
        const p = checkout.productId ? await s.products.getById(checkout.productId) : null;
        await handleProductGone(ctx, checkout, p);
        return;
      }
      await s.checkout.update(ctx.customer.id, nonce, { quantity: null, editingField: null });
      await reply(ctx, `⚠️ На жаль, зараз доступно лише ${result.available} шт. цього набору. Оберіть іншу кількість.`);
      const refreshed = await s.checkout.getActive(ctx.customer.id);
      if (refreshed) await promptStep(ctx, refreshed);
      return;
    }
  }
}

/** Перевіряє, що кнопка належить поточному оформленню. */
async function activeCheckout(ctx: BotContext, nonce: number): Promise<Checkout | null> {
  const checkout = await ctx.services.checkout.getActive(ctx.customer.id);
  if (!checkout || checkout.nonce !== nonce) {
    await answerCb(ctx, "Ця кнопка вже неактуальна", true);
    return null;
  }
  await answerCb(ctx);
  return checkout;
}

export function registerCheckoutHandlers(bot: Telegraf<BotContext>): void {
  bot.action(/^buy:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    await startCheckout(ctx, { productId: Number(ctx.match[1]) });
  });

  bot.action(/^ck:q:(\d+):(\d+)$/, async (ctx) => {
    const checkout = await activeCheckout(ctx, Number(ctx.match[1]));
    if (!checkout) return;
    await clearButtons(ctx);
    await setQuantity(ctx, checkout, Number(ctx.match[2]));
  });

  bot.action(/^ck:pay:(\d+):(\w+)$/, async (ctx) => {
    const checkout = await activeCheckout(ctx, Number(ctx.match[1]));
    if (!checkout) return;
    const method: PaymentMethod | null = paymentFromCode(ctx.match[2]!);
    if (!method || !ctx.services.config.shop.paymentMethods.includes(method)) {
      await promptStep(ctx, checkout);
      return;
    }
    await clearButtons(ctx);
    await saveAndContinue(ctx, checkout, { paymentMethod: method });
  });

  bot.action(/^ck:reuse:(\d+):([yn])$/, async (ctx) => {
    const checkout = await activeCheckout(ctx, Number(ctx.match[1]));
    if (!checkout) return;
    await clearButtons(ctx);
    await reuseProfile(ctx, checkout, ctx.match[2] === "y");
  });

  bot.action(/^ck:ok:(\d+)$/, async (ctx) => {
    await answerCb(ctx, "Оформлюємо…");
    await confirmOrder(ctx, Number(ctx.match[1]));
  });

  bot.action(/^ck:edit:(\d+)$/, async (ctx) => {
    const checkout = await activeCheckout(ctx, Number(ctx.match[1]));
    if (!checkout) return;
    await clearButtons(ctx);
    await showEditMenu(ctx, checkout);
  });

  bot.action(/^ck:ef:(\d+):([A-Z_]+)$/, async (ctx) => {
    const checkout = await activeCheckout(ctx, Number(ctx.match[1]));
    if (!checkout) return;
    const field = ctx.match[2] as CheckoutEditField;
    if (!EDIT_FIELDS.some((f) => f.field === field)) return;
    await clearButtons(ctx);
    const updated = await ctx.services.checkout.update(ctx.customer.id, checkout.nonce, {
      editingField: field,
      step: field,
    });
    if (updated) await promptStep(ctx, updated);
  });

  bot.action(/^ck:sum:(\d+)$/, async (ctx) => {
    const checkout = await activeCheckout(ctx, Number(ctx.match[1]));
    if (!checkout) return;
    await clearButtons(ctx);
    const updated = await ctx.services.checkout.update(ctx.customer.id, checkout.nonce, { editingField: null });
    if (updated) await promptStep(ctx, updated);
  });

  bot.action(/^ck:x:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    await clearButtons(ctx);
    await cancelCheckout(ctx, Number(ctx.match[1]));
  });

  bot.action("ck:go", async (ctx) => {
    await answerCb(ctx);
    const checkout = await ctx.services.checkout.getActive(ctx.customer.id);
    if (!checkout) {
      await reply(ctx, "Немає незавершеного оформлення. Оберіть набір у каталозі 🧱", {
        inline_keyboard: [[btn.callback("🧱 Каталог", cb.catalog())]],
      });
      return;
    }
    await clearButtons(ctx);
    await promptStep(ctx, checkout);
  });

  bot.action(/^ck:pick:(\d+):(\d+)$/, async (ctx) => {
    const checkout = await activeCheckout(ctx, Number(ctx.match[1]));
    if (!checkout) return;
    await clearButtons(ctx);
    await chooseProduct(ctx, checkout, Number(ctx.match[2]));
  });

  // Номер телефону через кнопку «Надіслати мій номер»
  bot.on(message("contact"), async (ctx) => {
    const checkout = await ctx.services.checkout.getActive(ctx.customer.id);
    if (!checkout || currentStep(checkout) !== "PHONE") {
      await ctx.reply("Дякую! Номер телефону знадобиться під час оформлення замовлення.", {
        reply_markup: mainMenu(ctx.isAdmin).reply_markup,
      });
      return;
    }
    const result = normalizePhone(ctx.message.contact.phone_number);
    if (result.ok) await ctx.reply("✅ Телефон збережено", { reply_markup: mainMenu(ctx.isAdmin).reply_markup });
    await applyValidated(ctx, checkout, result, (phone) => ({ phone }));
  });
}

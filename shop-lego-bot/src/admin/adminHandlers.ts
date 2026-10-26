import type { Telegraf } from "telegraf";
import type { InlineKeyboardButton } from "telegraf/types";
import type { OrderStatus } from "../generated/prisma/client.js";
import { cb } from "../bot/callbackData.js";
import type { BotContext } from "../bot/context.js";
import { MENU, btn, chunk, mainMenu } from "../bot/keyboards.js";
import { HTML, answerCb, reply, replyOrEdit } from "../bot/ui.js";
import { BOX_LABELS, COMPLETENESS_LABELS, CONDITION_LABELS, productTitle } from "../catalog/productPresenter.js";
import type { ProductPatch, ProductView } from "../catalog/productService.js";
import { DomainError, errorMessage } from "../lib/errors.js";
import { escapeHtml, truncate } from "../lib/format.js";
import { logger } from "../lib/logger.js";
import {
  parseNonNegativeInt,
  parsePositiveInt,
  parsePrice,
  validateImageUrl,
  validateLongText,
  validateProductName,
  validateSetNumber,
  validateTheme,
  validateTrackingNumber,
  type ValidationResult,
} from "../lib/validation.js";
import { ORDER_STATUS_LABELS, canTransition } from "../orders/orderStatus.js";
import {
  ADMIN_PAGE_SIZE,
  adminMenuView,
  customerListView,
  customerView,
  isOrderFilter,
  isProductFilter,
  orderListView,
  orderView,
  productAdminView,
  productHistoryView,
  productListView,
  statsView,
  type View,
} from "./adminViews.js";
import {
  WIZARD_SCENE,
  handleWizardButton,
  handleWizardPhoto,
  handleWizardText,
  saveWizard,
  startProductWizard,
  type WizardData,
} from "./productWizard.js";

/** Сцени адміністратора (стан зберігається в БД). */
const SCENE = {
  editField: "pe",
  stock: "ps",
  find: "find",
  tracking: "ttn",
  broadcast: "bc",
  orderLookup: "oq",
} as const;

type FindPurpose = "edit" | "stock" | "delete";

const adminId = (ctx: BotContext) => BigInt(ctx.from!.id);

async function show(ctx: BotContext, view: View, edit = false): Promise<void> {
  if (edit) await replyOrEdit(ctx, view.text, view.markup);
  else await reply(ctx, view.text, view.markup);
}

// ───────────────────────────── Товари ─────────────────────────────

type EditableKey =
  | "name"
  | "setNumber"
  | "theme"
  | "pieces"
  | "ageMin"
  | "price"
  | "conditionNote"
  | "description"
  | "lowStockThreshold"
  | "image";

const TEXT_FIELDS: Record<EditableKey, { prompt: string; clearable: boolean }> = {
  name: { prompt: "Введіть нову <b>назву</b> набору:", clearable: false },
  setNumber: { prompt: "Введіть <b>номер набору</b> (або «-», щоб очистити):", clearable: true },
  theme: { prompt: "Введіть <b>тематику</b>, наприклад: LEGO Technic", clearable: false },
  pieces: { prompt: "Введіть <b>кількість деталей</b> (або «-», якщо невідомо):", clearable: true },
  ageMin: { prompt: "Введіть <b>рекомендований вік</b> «від» (число) або «-»:", clearable: true },
  price: { prompt: "Введіть нову <b>ціну</b> в гривнях:", clearable: false },
  conditionNote: { prompt: "Введіть <b>примітку щодо стану</b> (або «-», щоб очистити):", clearable: true },
  description: { prompt: "Введіть <b>опис</b> (або «-», щоб очистити):", clearable: true },
  lowStockThreshold: { prompt: "Введіть <b>поріг «залишилося мало»</b> (число):", clearable: false },
  image: { prompt: "Надішліть <b>фото</b> або посилання https://… (або «-», щоб прибрати фото):", clearable: true },
};

function parseFieldValue(field: EditableKey, text: string): ValidationResult<ProductPatch> {
  const clear = text.trim() === "-";
  if (clear && TEXT_FIELDS[field].clearable) {
    if (field === "image") return { ok: true, value: { imageUrl: null, telegramFileId: null } };
    return { ok: true, value: { [field]: null } as ProductPatch };
  }
  const map = <T>(r: ValidationResult<T>, f: (v: T) => ProductPatch): ValidationResult<ProductPatch> =>
    r.ok ? { ok: true, value: f(r.value) } : r;
  switch (field) {
    case "name":
      return map(validateProductName(text), (name) => ({ name }));
    case "setNumber":
      return map(validateSetNumber(text), (setNumber) => ({ setNumber }));
    case "theme":
      return map(validateTheme(text), (theme) => ({ theme }));
    case "pieces":
      return map(parsePositiveInt(text, 100_000), (pieces) => ({ pieces }));
    case "ageMin":
      return map(parseNonNegativeInt(text.replace("+", ""), 99), (ageMin) => ({ ageMin }));
    case "price":
      return map(parsePrice(text), (price) => ({ price }));
    case "conditionNote":
      return map(validateLongText(text, 500), (conditionNote) => ({ conditionNote }));
    case "description":
      return map(validateLongText(text, 2000), (description) => ({ description }));
    case "lowStockThreshold":
      return map(parseNonNegativeInt(text, 1000), (lowStockThreshold) => ({ lowStockThreshold }));
    case "image":
      return map(validateImageUrl(text), (imageUrl) => ({ imageUrl, telegramFileId: null }));
  }
}

const ENUM_FIELDS = {
  condition: CONDITION_LABELS,
  boxState: BOX_LABELS,
  completeness: COMPLETENESS_LABELS,
} as const;

async function showProduct(ctx: BotContext, productId: number, edit = false): Promise<void> {
  const p = await ctx.services.products.getById(productId);
  if (!p) {
    await reply(ctx, "Товар не знайдено.");
    return;
  }
  await show(ctx, productAdminView(p), edit);
}

async function lookupProducts(ctx: BotContext, query: string, purpose: FindPurpose): Promise<void> {
  const found = await ctx.services.products.adminLookup(query);
  if (found.length === 0) {
    await reply(ctx, `Нічого не знайдено за запитом «${escapeHtml(query)}». Спробуйте номер набору, назву або код товару (#12).`);
    return;
  }
  if (found.length === 1) {
    await onProductChosen(ctx, found[0]!, purpose);
    return;
  }
  const rows: InlineKeyboardButton[][] = found.slice(0, 10).map((p) => [
    btn.callback(
      `#${p.id} ${truncate(productTitle(p), 40)}${p.status === "ARCHIVED" ? " 🗄" : ""}`,
      purpose === "stock"
        ? cb.adminProductStock(p.id, "add")
        : purpose === "delete"
          ? cb.adminProductArchive(p.id)
          : cb.adminProduct(p.id),
    ),
  ]);
  await reply(ctx, "Знайдено кілька товарів, оберіть потрібний:", { inline_keyboard: rows });
}

async function onProductChosen(ctx: BotContext, p: ProductView, purpose: FindPurpose): Promise<void> {
  if (purpose === "stock") return promptStockChange(ctx, p.id, "add");
  if (purpose === "delete") return promptArchive(ctx, p.id);
  return showProduct(ctx, p.id);
}

async function promptArchive(ctx: BotContext, productId: number): Promise<void> {
  const p = await ctx.services.products.getById(productId);
  if (!p) return reply(ctx, "Товар не знайдено.");
  if (p.status === "ARCHIVED") {
    await reply(ctx, `Товар #${p.id} уже в архіві.`, {
      inline_keyboard: [[btn.callback("♻️ Відновити", cb.adminProductRestore(p.id))]],
    });
    return;
  }
  await reply(
    ctx,
    `🗄 Архівувати <b>${escapeHtml(productTitle(p))}</b>?\nТовар зникне з каталогу для покупців. Історія замовлень і залишки збережуться, товар можна відновити.${
      p.stockReserved > 0 ? `\n⚠️ У резерві ${p.stockReserved} шт. під активні замовлення — їх буде виконано як зазвичай.` : ""
    }`,
    {
      inline_keyboard: [
        [btn.callback("🗄 Так, архівувати", cb.adminProductArchiveConfirm(p.id)), btn.callback("Скасувати", cb.adminProduct(p.id))],
      ],
    },
  );
}

async function promptStockChange(ctx: BotContext, productId: number, mode: "add" | "sub"): Promise<void> {
  const p = await ctx.services.products.getById(productId);
  if (!p) return reply(ctx, "Товар не знайдено.");
  await ctx.services.userState.set(adminId(ctx), SCENE.stock, { productId, mode });
  await reply(
    ctx,
    `${mode === "add" ? "➕ <b>Надходження на склад</b>" : "➖ <b>Списання зі складу</b>"}\n${escapeHtml(productTitle(p))}\nЗараз: на складі ${p.stockOnHand}, у резерві ${p.stockReserved}, доступно ${p.available}.\n\nВведіть кількість${
      mode === "add" ? "" : " (не більше " + p.available + ")"
    } і, за бажанням, коментар: <i>${mode === "add" ? "3 нова поставка" : "1 пошкоджена коробка"}</i>`,
    { inline_keyboard: [[btn.callback("❌ Скасувати", cb.adminCancelScene())]] },
  );
}

async function applyStockChange(ctx: BotContext, data: { productId: number; mode: "add" | "sub" }, text: string) {
  const m = /^\s*(\d{1,6})\s*(.*)$/su.exec(text);
  const qty = m ? Number(m[1]) : NaN;
  if (!m || !Number.isInteger(qty) || qty <= 0) {
    await reply(ctx, "⚠️ Введіть додатне ціле число, наприклад: 3");
    return;
  }
  const note = m[2]?.trim().slice(0, 200) || undefined;
  const s = ctx.services;
  try {
    const levels =
      data.mode === "add"
        ? await s.inventory.addStock(data.productId, qty, adminId(ctx), note ?? "Надходження на склад")
        : await s.inventory.adjustStock(data.productId, -qty, adminId(ctx), note ?? "Списання власником");
    await s.userState.clear(adminId(ctx));
    await reply(
      ctx,
      `✅ ${data.mode === "add" ? `Додано ${qty} шт.` : `Списано ${qty} шт.`}\nНа складі: <b>${levels.onHand}</b>, у резерві: ${levels.reserved}, доступно покупцям: <b>${levels.available}</b>.`,
    );
    await showProduct(ctx, data.productId);
  } catch (err) {
    if (err instanceof DomainError) await reply(ctx, `⚠️ ${escapeHtml(err.message)}`);
    else throw err;
  }
}

// ───────────────────────────── Замовлення ─────────────────────────────

async function showOrder(ctx: BotContext, orderId: number, edit = false): Promise<void> {
  const order = await ctx.services.orders.getOrder(orderId);
  if (!order) {
    await reply(ctx, `Замовлення №${orderId} не знайдено.`);
    return;
  }
  await show(ctx, orderView(order, ctx.services.config.shop.timezone), edit);
}

async function changeOrderStatus(
  ctx: BotContext,
  orderId: number,
  to: OrderStatus,
  opts: { trackingNumber?: string | null; edit?: boolean } = {},
): Promise<void> {
  const s = ctx.services;
  try {
    const result = await s.orders.changeStatus({
      orderId,
      to,
      actor: { actorType: "ADMIN", actorTelegramId: adminId(ctx) },
      trackingNumber: opts.trackingNumber ?? null,
    });
    await answerCb(ctx, result.changed ? `Статус: ${ORDER_STATUS_LABELS[to]}` : "Статус уже встановлено");
    if (result.changed) {
      logger.info({ orderId, to, admin: ctx.from?.id }, "Статус замовлення змінено");
      // Сповіщення покупцю — одразу, без очікування фонового обробника.
      await s.notifications.processDue({ orderId }).catch((err) => logger.error({ err }, "Помилка надсилання сповіщення"));
    }
  } catch (err) {
    if (err instanceof DomainError) {
      await answerCb(ctx, err.message, true);
      if (!ctx.callbackQuery) await reply(ctx, `⚠️ ${escapeHtml(err.message)}`);
    } else throw err;
  }
  await showOrder(ctx, orderId, opts.edit ?? true);
}

async function onStatusButton(ctx: BotContext, orderId: number, to: OrderStatus, confirmed: boolean): Promise<void> {
  const order = await ctx.services.orders.getOrder(orderId);
  if (!order) {
    await answerCb(ctx, "Замовлення не знайдено", true);
    return;
  }
  if (!canTransition(order.status, to)) {
    await answerCb(ctx, `Неможливо: зараз статус «${ORDER_STATUS_LABELS[order.status]}»`, true);
    await showOrder(ctx, orderId, true);
    return;
  }
  if (!confirmed && (to === "CANCELED" || to === "RETURNED")) {
    await answerCb(ctx);
    const question =
      to === "CANCELED"
        ? `Скасувати замовлення №${orderId}? Зарезервований товар повернеться в доступний залишок, покупець отримає повідомлення.`
        : `Оформити повернення за замовленням №${orderId}? Після фактичного отримання товару підтвердьте повернення на склад.`;
    await replyOrEdit(ctx, question, {
      inline_keyboard: [
        [btn.callback(to === "CANCELED" ? "❌ Так, скасувати" : "↩️ Так, повернення", cb.adminOrderStatusConfirm(orderId, to))],
        [btn.callback("⬅️ Назад до замовлення", cb.adminOrder(orderId))],
      ],
    });
    return;
  }
  if (!confirmed && to === "SHIPPED") {
    await answerCb(ctx);
    await ctx.services.userState.set(adminId(ctx), SCENE.tracking, { orderId });
    await replyOrEdit(ctx, `🚚 Замовлення №${orderId}: введіть номер ТТН, щоб надіслати його покупцю, або продовжте без нього.`, {
      inline_keyboard: [
        [btn.callback("🚚 Відправлено без ТТН", cb.adminOrderStatusConfirm(orderId, "SHIPPED"))],
        [btn.callback("⬅️ Назад до замовлення", cb.adminOrder(orderId))],
      ],
    });
    return;
  }
  if (to === "SHIPPED") await ctx.services.userState.clear(adminId(ctx));
  await changeOrderStatus(ctx, orderId, to);
}

// ───────────────────────────── Розсилка ─────────────────────────────

async function promptBroadcast(ctx: BotContext): Promise<void> {
  await ctx.services.userState.set(adminId(ctx), SCENE.broadcast, {});
  const count = await ctx.services.broadcasts.recipientsCount();
  await reply(
    ctx,
    `📣 <b>Розсилка</b>\nОтримувачів зараз: ${count} (без тих, хто відписався чи заблокував бота).\n\nНадішліть текст повідомлення (можна фото з підписом). Перед надсиланням я покажу попередній перегляд і попрошу підтвердження.`,
    { inline_keyboard: [[btn.callback("❌ Скасувати", cb.adminCancelScene())]] },
  );
}

async function prepareBroadcast(ctx: BotContext, text: string, photoFileId: string | null): Promise<void> {
  const s = ctx.services;
  const valid = validateLongText(text, photoFileId ? 1000 : 3500);
  // Фото без підпису допустиме; задовгий підпис чи порожній текст без фото — ні.
  if (!valid.ok && (text.trim().length > 0 || !photoFileId)) {
    await reply(ctx, `⚠️ ${escapeHtml(valid.error)}`);
    return;
  }
  const body = valid.ok ? escapeHtml(valid.value) : "";
  const draft = await s.broadcasts.createDraft(adminId(ctx), body, photoFileId);
  await s.userState.clear(adminId(ctx));
  const count = await s.broadcasts.recipientsCount();
  await reply(ctx, "👀 <b>Попередній перегляд:</b>");
  if (photoFileId) await ctx.replyWithPhoto(photoFileId, { caption: body, parse_mode: "HTML" });
  else await ctx.reply(body, HTML);
  await reply(ctx, `Надіслати це повідомлення <b>${count}</b> покупцям? (розсилка №${draft.id})`, {
    inline_keyboard: [
      [btn.callback("✅ Так, надіслати", cb.adminBroadcastConfirm()), btn.callback("❌ Скасувати", cb.adminBroadcastCancel())],
    ],
  });
}

// ───────────────────────────── Текст і фото в сценах ─────────────────────────────

/** Обробляє текст адміністратора в активній сцені. Повертає false, якщо сцени немає. */
export async function handleAdminText(ctx: BotContext, text: string): Promise<boolean> {
  const s = ctx.services;
  const state = await s.userState.get<Record<string, unknown>>(adminId(ctx));
  if (!state.scene) return false;
  switch (state.scene) {
    case WIZARD_SCENE:
      await handleWizardText(ctx, state.data as unknown as WizardData, text);
      return true;
    case SCENE.editField: {
      const { productId, field } = state.data as { productId: number; field: EditableKey };
      const parsed = parseFieldValue(field, text);
      if (!parsed.ok) {
        await reply(ctx, `⚠️ ${escapeHtml(parsed.error)}`);
        return true;
      }
      await s.products.update(productId, parsed.value, adminId(ctx));
      await s.userState.clear(adminId(ctx));
      await reply(ctx, "✅ Збережено.");
      await showProduct(ctx, productId);
      return true;
    }
    case SCENE.stock:
      await applyStockChange(ctx, state.data as { productId: number; mode: "add" | "sub" }, text);
      return true;
    case SCENE.find: {
      const { purpose } = state.data as { purpose: FindPurpose };
      await s.userState.clear(adminId(ctx));
      await lookupProducts(ctx, text, purpose);
      return true;
    }
    case SCENE.tracking: {
      const { orderId } = state.data as { orderId: number };
      const r = validateTrackingNumber(text);
      if (!r.ok) {
        await reply(ctx, `⚠️ ${escapeHtml(r.error)}`);
        return true;
      }
      await s.userState.clear(adminId(ctx));
      await changeOrderStatus(ctx, orderId, "SHIPPED", { trackingNumber: r.value, edit: false });
      return true;
    }
    case SCENE.broadcast:
      await prepareBroadcast(ctx, text, null);
      return true;
    case SCENE.orderLookup: {
      await s.userState.clear(adminId(ctx));
      const id = Number(text.replace(/[^\d]/g, ""));
      if (!id) await reply(ctx, "Введіть номер замовлення, наприклад: 104");
      else await showOrder(ctx, id);
      return true;
    }
    default:
      await s.userState.clear(adminId(ctx));
      return false;
  }
}

/** Фото від адміністратора: фото товару в майстрі/редагуванні або фото для розсилки. */
export async function handleAdminPhoto(ctx: BotContext, fileId: string, caption: string | undefined): Promise<boolean> {
  const s = ctx.services;
  const state = await s.userState.get<Record<string, unknown>>(adminId(ctx));
  if (state.scene === WIZARD_SCENE) {
    await handleWizardPhoto(ctx, state.data as unknown as WizardData, fileId);
    return true;
  }
  if (state.scene === SCENE.editField && (state.data as { field?: string }).field === "image") {
    const { productId } = state.data as { productId: number };
    await s.products.update(productId, { telegramFileId: fileId, imageUrl: null }, adminId(ctx));
    await s.userState.clear(adminId(ctx));
    await reply(ctx, "✅ Фото оновлено.");
    await showProduct(ctx, productId);
    return true;
  }
  if (state.scene === SCENE.broadcast) {
    await prepareBroadcast(ctx, caption ?? "", fileId);
    return true;
  }
  return false;
}

// ───────────────────────────── Реєстрація ─────────────────────────────

export function registerAdminHandlers(bot: Telegraf<BotContext>): void {
  const adminCommand = (name: string, handler: (ctx: BotContext, args: string) => Promise<void>) => {
    bot.command(name, async (ctx) => {
      if (!ctx.isAdmin) {
        await reply(ctx, "⛔ Ця команда доступна лише власнику магазину.");
        return;
      }
      const args = ctx.message.text.replace(/^\/\S+\s*/, "").trim();
      await handler(ctx, args);
    });
  };

  // Усі кнопки адмін-панелі — лише для адміністраторів
  bot.action(/^a:/, async (ctx, next) => {
    if (!ctx.isAdmin) {
      await answerCb(ctx, "⛔ Недоступно", true);
      return;
    }
    return next();
  });

  const openMenu = async (ctx: BotContext) => show(ctx, await adminMenuView(ctx.services));
  adminCommand("admin", openMenu);
  bot.hears(MENU.admin, async (ctx) => {
    if (ctx.isAdmin) await openMenu(ctx);
  });
  bot.action("a:menu", async (ctx) => {
    await answerCb(ctx);
    await show(ctx, await adminMenuView(ctx.services), true);
  });

  // Товари
  adminCommand("addproduct", async (ctx) => startProductWizard(ctx));
  bot.action("a:new", async (ctx) => {
    await answerCb(ctx);
    await startProductWizard(ctx);
  });

  const findCommand = (purpose: FindPurpose, prompt: string) => async (ctx: BotContext, args: string) => {
    if (args) {
      await lookupProducts(ctx, args, purpose);
      return;
    }
    await ctx.services.userState.set(adminId(ctx), SCENE.find, { purpose });
    await reply(ctx, prompt, { inline_keyboard: [[btn.callback("❌ Скасувати", cb.adminCancelScene())]] });
  };
  adminCommand("editproduct", findCommand("edit", "✏️ Введіть номер набору, назву або код товару (#12):"));
  adminCommand("deleteproduct", findCommand("delete", "🗄 Який товар архівувати? Введіть номер набору, назву або код (#12):"));
  bot.action("a:find", async (ctx) => {
    await answerCb(ctx);
    await findCommand("edit", "✏️ Введіть номер набору, назву або код товару (#12):")(ctx, "");
  });

  adminCommand("stock", async (ctx) => {
    const { items, total } = await ctx.services.products.listForAdmin({ filter: "active", limit: ADMIN_PAGE_SIZE, offset: 0 });
    await show(ctx, productListView(items, total, "active", 1));
  });
  bot.action(/^a:pl:(\w+):(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    const filter = ctx.match[1]!;
    if (!isProductFilter(filter)) return;
    const page = Math.max(1, Number(ctx.match[2]));
    const { items, total } = await ctx.services.products.listForAdmin({
      filter,
      limit: ADMIN_PAGE_SIZE,
      offset: (page - 1) * ADMIN_PAGE_SIZE,
    });
    await show(ctx, productListView(items, total, filter, page), true);
  });

  adminCommand("addstock", async (ctx, args) => {
    // /addstock 42151 3 [коментар] — швидке надходження
    const m = /^(\S+)\s+(\d{1,6})(?:\s+(.+))?$/su.exec(args);
    if (m) {
      const found = (await ctx.services.products.adminLookup(m[1]!)).filter((p) => p.status === "ACTIVE");
      if (found.length === 1) {
        await applyStockChange(ctx, { productId: found[0]!.id, mode: "add" }, `${m[2]} ${m[3] ?? ""}`);
        return;
      }
      await lookupProducts(ctx, m[1]!, "stock");
      return;
    }
    await findCommand("stock", "➕ До якого товару додати надходження? Введіть номер набору, назву або код (#12):")(ctx, args);
  });

  bot.action(/^a:pv:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    await showProduct(ctx, Number(ctx.match[1]), true);
  });
  bot.action(/^a:pe:(\d+):(\w+)$/, async (ctx) => {
    await answerCb(ctx);
    const productId = Number(ctx.match[1]);
    const field = ctx.match[2]!;
    if (field in ENUM_FIELDS) {
      const labels = ENUM_FIELDS[field as keyof typeof ENUM_FIELDS] as Record<string, string>;
      const rows = chunk(
        Object.entries(labels).map(([value, label]) => btn.callback(label, cb.adminProductEnum(productId, field, value))),
        1,
      );
      rows.push([btn.callback("⬅️ Назад", cb.adminProduct(productId))]);
      await replyOrEdit(ctx, "Оберіть нове значення:", { inline_keyboard: rows });
      return;
    }
    if (!(field in TEXT_FIELDS)) return;
    await ctx.services.userState.set(adminId(ctx), SCENE.editField, { productId, field });
    await reply(ctx, TEXT_FIELDS[field as EditableKey].prompt, {
      inline_keyboard: [[btn.callback("❌ Скасувати", cb.adminCancelScene())]],
    });
  });
  bot.action(/^a:pev:(\d+):(\w+):(\w+)$/, async (ctx) => {
    const productId = Number(ctx.match[1]);
    const field = ctx.match[2]! as keyof typeof ENUM_FIELDS;
    const value = ctx.match[3]!;
    const labels = ENUM_FIELDS[field] as Record<string, string> | undefined;
    if (!labels || !(value in labels)) {
      await answerCb(ctx, "Некоректне значення", true);
      return;
    }
    await ctx.services.products.update(productId, { [field]: value } as ProductPatch, adminId(ctx));
    await answerCb(ctx, "Збережено");
    await showProduct(ctx, productId, true);
  });
  bot.action(/^a:ph:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    const p = await ctx.services.products.getById(Number(ctx.match[1]));
    if (p) await show(ctx, await productHistoryView(ctx.services, p));
  });
  bot.action(/^a:ps:(\d+):(add|sub)$/, async (ctx) => {
    await answerCb(ctx);
    await promptStockChange(ctx, Number(ctx.match[1]), ctx.match[2] as "add" | "sub");
  });
  bot.action(/^a:pa:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    await promptArchive(ctx, Number(ctx.match[1]));
  });
  bot.action(/^a:pa!:(\d+)$/, async (ctx) => {
    const p = await ctx.services.products.setStatus(Number(ctx.match[1]), "ARCHIVED", adminId(ctx));
    await answerCb(ctx, "Товар архівовано");
    await show(ctx, productAdminView(p), true);
  });
  bot.action(/^a:pr:(\d+)$/, async (ctx) => {
    const p = await ctx.services.products.setStatus(Number(ctx.match[1]), "ACTIVE", adminId(ctx));
    await answerCb(ctx, "Товар відновлено");
    await show(ctx, productAdminView(p), true);
  });

  // Майстер додавання товару
  bot.action(/^a:np:(\w+):(\w+)$/, async (ctx) => {
    await answerCb(ctx);
    const state = await ctx.services.userState.get<WizardData>(adminId(ctx));
    if (state.scene !== WIZARD_SCENE) {
      await reply(ctx, "Майстер додавання вже завершено. Почніть знову: /addproduct");
      return;
    }
    await handleWizardButton(ctx, state.data, ctx.match[1]!, ctx.match[2]!);
  });
  bot.action("a:npok", async (ctx) => {
    await answerCb(ctx);
    const state = await ctx.services.userState.get<WizardData>(adminId(ctx));
    if (state.scene !== WIZARD_SCENE) {
      await reply(ctx, "Цей набір уже збережено або майстер скасовано.");
      return;
    }
    await saveWizard(ctx, state.data);
  });
  bot.action("a:npre", async (ctx) => {
    await answerCb(ctx);
    await startProductWizard(ctx);
  });
  bot.action("a:npx", async (ctx) => {
    await answerCb(ctx);
    await ctx.services.userState.clear(adminId(ctx));
    await reply(ctx, "Додавання набору скасовано.");
  });
  bot.action("a:scx", async (ctx) => {
    await answerCb(ctx);
    await ctx.services.userState.clear(adminId(ctx));
    await reply(ctx, "Дію скасовано.", mainMenu(true).reply_markup);
  });

  // Замовлення
  adminCommand("orders", async (ctx, args) => {
    const filter = args && isOrderFilter(args) ? args : "new";
    const { items, total } = await ctx.services.orders.listOrders(filter, ADMIN_PAGE_SIZE, 0);
    await show(ctx, orderListView(items, total, filter, 1, ctx.services.config.shop.timezone));
  });
  bot.action(/^a:ol:(\w+):(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    const filter = ctx.match[1]!;
    if (!isOrderFilter(filter)) return;
    const page = Math.max(1, Number(ctx.match[2]));
    const { items, total } = await ctx.services.orders.listOrders(filter, ADMIN_PAGE_SIZE, (page - 1) * ADMIN_PAGE_SIZE);
    await show(ctx, orderListView(items, total, filter, page, ctx.services.config.shop.timezone), true);
  });
  adminCommand("order", async (ctx, args) => {
    const id = Number(args.replace(/[^\d]/g, ""));
    if (id) {
      await showOrder(ctx, id);
      return;
    }
    await ctx.services.userState.set(adminId(ctx), SCENE.orderLookup, {});
    await reply(ctx, "🔎 Введіть номер замовлення:", { inline_keyboard: [[btn.callback("❌ Скасувати", cb.adminCancelScene())]] });
  });
  bot.action(/^a:ov:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    await showOrder(ctx, Number(ctx.match[1]), true);
  });
  bot.action(/^a:os(!?):(\d+):([A-Z_]+)$/, async (ctx) => {
    const to = ctx.match[3] as OrderStatus;
    if (!(to in ORDER_STATUS_LABELS)) {
      await answerCb(ctx, "Невідомий статус", true);
      return;
    }
    await onStatusButton(ctx, Number(ctx.match[2]), to, ctx.match[1] === "!");
  });
  bot.action(/^a:ors:(\d+):([01])$/, async (ctx) => {
    const orderId = Number(ctx.match[1]);
    try {
      await ctx.services.orders.resolveReturn({ orderId, restock: ctx.match[2] === "1", actorTelegramId: adminId(ctx) });
      await answerCb(ctx, ctx.match[2] === "1" ? "Товар повернуто на склад" : "Повернення закрито без повернення на склад");
      await ctx.services.notifications.processDue({ orderId }).catch(() => undefined);
    } catch (err) {
      await answerCb(ctx, err instanceof DomainError ? err.message : errorMessage(err), true);
    }
    await showOrder(ctx, orderId, true);
  });

  // Покупці
  adminCommand("customers", async (ctx) => show(ctx, await customerListView(ctx.services, 1)));
  bot.action(/^a:cl:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    await show(ctx, await customerListView(ctx.services, Math.max(1, Number(ctx.match[1]))), true);
  });
  bot.action(/^a:cv:(\d+)$/, async (ctx) => {
    await answerCb(ctx);
    const view = await customerView(ctx.services, Number(ctx.match[1]));
    if (view) await show(ctx, view, true);
    else await reply(ctx, "Покупця не знайдено.");
  });

  // Статистика
  adminCommand("stats", async (ctx) => show(ctx, statsView(await ctx.services.stats.summary(ctx.services.config.shop.timezone))));
  bot.action("a:st", async (ctx) => {
    await answerCb(ctx);
    await show(ctx, statsView(await ctx.services.stats.summary(ctx.services.config.shop.timezone)), true);
  });

  // Розсилка (з обов'язковим підтвердженням)
  adminCommand("broadcast", promptBroadcast);
  bot.action("a:bc:new", async (ctx) => {
    await answerCb(ctx);
    await promptBroadcast(ctx);
  });
  bot.action("a:bc:ok", async (ctx) => {
    const s = ctx.services;
    const draft = await s.broadcasts.latestDraft(adminId(ctx));
    if (!draft) {
      await answerCb(ctx, "Немає розсилки, що очікує підтвердження", true);
      return;
    }
    const started = await s.broadcasts.confirm(draft.id);
    await answerCb(ctx, started ? "Розсилку запущено" : "Розсилку вже запущено");
    await ctx.editMessageReplyMarkup(undefined).catch(() => undefined);
    if (started) {
      logger.info({ broadcastId: started.id, recipients: started.totalRecipients }, "Розсилку запущено");
      await reply(ctx, `📣 Розсилку №${started.id} запущено для ${started.totalRecipients} покупців. Я повідомлю, коли вона завершиться.`);
    }
  });
  bot.action("a:bc:x", async (ctx) => {
    await answerCb(ctx);
    await ctx.services.broadcasts.cancelDraft(adminId(ctx));
    await ctx.editMessageReplyMarkup(undefined).catch(() => undefined);
    await reply(ctx, "Розсилку скасовано.");
  });
}

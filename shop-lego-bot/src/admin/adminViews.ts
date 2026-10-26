import type { InlineKeyboardButton, InlineKeyboardMarkup } from "telegraf/types";
import type { OrderStatus } from "../generated/prisma/client.js";
import { cb } from "../bot/callbackData.js";
import { btn, chunk } from "../bot/keyboards.js";
import { adminProductCard, productShortTitle, productTitle } from "../catalog/productPresenter.js";
import type { ProductView } from "../catalog/productService.js";
import { escapeHtml, formatDate, formatDateTime, formatMoney, truncate } from "../lib/format.js";
import { adminOrderDetailsText } from "../orders/orderPresenter.js";
import { ORDER_STATUS_ACTIONS, ORDER_STATUS_EMOJI, ORDER_STATUS_LABELS, ORDER_TRANSITIONS } from "../orders/orderStatus.js";
import type { OrderListFilter } from "../orders/orderService.js";
import type { OrderFull, OrderWithHistory } from "../orders/types.js";
import type { Services } from "../services.js";
import type { ShopStats } from "./statsService.js";

export interface View {
  text: string;
  markup: InlineKeyboardMarkup;
}

export const ADMIN_PAGE_SIZE = 10;

export async function adminMenuView(s: Services): Promise<View> {
  const [newOrders, lowStock] = await Promise.all([
    s.prisma.order.count({ where: { status: { in: ["NEW", "AWAITING_CONFIRMATION"] } } }),
    s.products.listLowStock(),
  ]);
  const text = [
    `⚙️ <b>Адмін-панель «${escapeHtml(s.config.shop.name)}»</b>`,
    "",
    `🆕 Замовлень очікують підтвердження: <b>${newOrders}</b>`,
    `⚠️ Товарів, що закінчуються: <b>${lowStock.length}</b>`,
    "",
    "Команди: /addproduct /editproduct /deleteproduct /stock /addstock /orders /order /customers /stats /broadcast",
  ].join("\n");
  return {
    text,
    markup: {
      inline_keyboard: [
        [btn.callback("🆕 Нові замовлення", cb.adminOrders("new", 1)), btn.callback("⚙️ В роботі", cb.adminOrders("work", 1))],
        [btn.callback("📋 Усі замовлення", cb.adminOrders("all", 1)), btn.callback("↩️ Повернення", cb.adminOrders("returns", 1))],
        [btn.callback("➕ Додати набір", cb.adminNewProduct()), btn.callback("✏️ Знайти набір", cb.adminFindProduct())],
        [btn.callback("📦 Залишки", cb.adminProducts("active", 1)), btn.callback("⚠️ Закінчуються", cb.adminProducts("low", 1))],
        [btn.callback("👥 Покупці", cb.adminCustomers(1)), btn.callback("📊 Статистика", cb.adminStats())],
        [btn.callback("📣 Розсилка", cb.adminBroadcastStart())],
      ],
    },
  };
}

const ORDER_FILTER_LABELS: Record<OrderListFilter, string> = {
  new: "🆕 Нові та ті, що очікують підтвердження",
  work: "⚙️ В роботі (підтверджені, оплачені, комплектуються)",
  shipped: "🚚 Відправлені",
  done: "🎉 Доставлені",
  canceled: "❌ Скасовані",
  returns: "↩️ Повернення",
  all: "📋 Усі замовлення",
};

export function isOrderFilter(v: string): v is OrderListFilter {
  return v in ORDER_FILTER_LABELS;
}

export function orderListView(
  orders: OrderFull[],
  total: number,
  filter: OrderListFilter,
  page: number,
  timezone: string,
): View {
  const pages = Math.max(1, Math.ceil(total / ADMIN_PAGE_SIZE));
  const lines = [`<b>${ORDER_FILTER_LABELS[filter]}</b> — ${total}`, ""];
  if (orders.length === 0) lines.push("Замовлень немає.");
  for (const o of orders) {
    const first = o.items[0];
    lines.push(
      `${ORDER_STATUS_EMOJI[o.status]} <b>№${o.id}</b> · ${formatDateTime(o.createdAt, timezone)} · ${escapeHtml(
        truncate(o.fullName, 24),
      )} · ${first ? escapeHtml(first.setNumber ?? truncate(first.productName, 20)) : ""}${
        first && first.quantity > 1 ? ` ×${first.quantity}` : ""
      } · ${formatMoney(o.totalAmount)} · ${ORDER_STATUS_LABELS[o.status]}`,
    );
  }
  const rows: InlineKeyboardButton[][] = chunk(
    orders.map((o) => btn.callback(`${ORDER_STATUS_EMOJI[o.status]} №${o.id}`, cb.adminOrder(o.id))),
    3,
  );
  const nav: InlineKeyboardButton[] = [];
  if (page > 1) nav.push(btn.callback("⬅️", cb.adminOrders(filter, page - 1)));
  if (pages > 1) nav.push(btn.callback(`${page}/${pages}`, cb.adminOrders(filter, page)));
  if (page < pages) nav.push(btn.callback("➡️", cb.adminOrders(filter, page + 1)));
  if (nav.length) rows.push(nav);
  rows.push([
    btn.callback("🆕 Нові", cb.adminOrders("new", 1)),
    btn.callback("⚙️ В роботі", cb.adminOrders("work", 1)),
    btn.callback("🚚 Відправлені", cb.adminOrders("shipped", 1)),
  ]);
  rows.push([
    btn.callback("🎉 Доставлені", cb.adminOrders("done", 1)),
    btn.callback("❌ Скасовані", cb.adminOrders("canceled", 1)),
    btn.callback("📋 Усі", cb.adminOrders("all", 1)),
  ]);
  rows.push([btn.callback("⬅️ Меню", cb.adminMenu())]);
  return { text: lines.join("\n"), markup: { inline_keyboard: rows } };
}

export function orderView(order: OrderWithHistory, timezone: string): View {
  const rows: InlineKeyboardButton[][] = [];
  const transitions = ORDER_TRANSITIONS[order.status].filter((s) => s !== "AWAITING_CONFIRMATION");
  rows.push(
    ...chunk(
      transitions.map((to: OrderStatus) => btn.callback(ORDER_STATUS_ACTIONS[to], cb.adminOrderStatus(order.id, to))),
      2,
    ),
  );
  if (order.status === "RETURNED" && order.stockState === "SHIPPED") {
    rows.push([btn.callback("📦 Товар повернувся на склад", cb.adminResolveReturn(order.id, true))]);
    rows.push([btn.callback("🗑 Не повертати на склад (брак)", cb.adminResolveReturn(order.id, false))]);
  }
  rows.push([
    btn.callback("👤 Покупець", cb.adminCustomer(order.customerId)),
    btn.callback("🔄 Оновити", cb.adminOrder(order.id)),
  ]);
  rows.push([btn.callback("⬅️ До замовлень", cb.adminOrders("all", 1))]);
  return { text: adminOrderDetailsText(order, timezone), markup: { inline_keyboard: rows } };
}

const PRODUCT_FILTER_LABELS: Record<string, string> = {
  active: "📦 Залишки (активні товари)",
  low: "⚠️ Закінчуються",
  out: "❌ Немає в наявності",
  archived: "🗄 Архів",
};

export function isProductFilter(v: string): v is "active" | "low" | "out" | "archived" {
  return v in PRODUCT_FILTER_LABELS;
}

export function productListView(
  items: ProductView[],
  total: number,
  filter: "active" | "low" | "out" | "archived",
  page: number,
): View {
  const pages = Math.max(1, Math.ceil(total / ADMIN_PAGE_SIZE));
  const lines = [
    `<b>${PRODUCT_FILTER_LABELS[filter]}</b> — ${total}`,
    "<i>на складі / у резерві / доступно</i>",
    "",
  ];
  if (items.length === 0) lines.push("Товарів немає.");
  for (const p of items) {
    lines.push(
      `<code>#${p.id}</code> ${escapeHtml(productShortTitle(p, 46))} — ${formatMoney(p.price)} · <b>${p.stockOnHand}/${p.stockReserved}/${p.available}</b>${
        p.availability === "LOW_STOCK" ? " ⚠️" : p.availability === "OUT_OF_STOCK" ? " ❌" : ""
      }`,
    );
  }
  const rows: InlineKeyboardButton[][] = chunk(
    items.map((p) => btn.callback(`#${p.id} ${truncate(p.setNumber ?? p.name, 14)}`, cb.adminProduct(p.id))),
    2,
  );
  const nav: InlineKeyboardButton[] = [];
  if (page > 1) nav.push(btn.callback("⬅️", cb.adminProducts(filter, page - 1)));
  if (pages > 1) nav.push(btn.callback(`${page}/${pages}`, cb.adminProducts(filter, page)));
  if (page < pages) nav.push(btn.callback("➡️", cb.adminProducts(filter, page + 1)));
  if (nav.length) rows.push(nav);
  rows.push([
    btn.callback("📦 Усі", cb.adminProducts("active", 1)),
    btn.callback("⚠️ Мало", cb.adminProducts("low", 1)),
    btn.callback("❌ Немає", cb.adminProducts("out", 1)),
    btn.callback("🗄 Архів", cb.adminProducts("archived", 1)),
  ]);
  rows.push([btn.callback("➕ Додати набір", cb.adminNewProduct()), btn.callback("⬅️ Меню", cb.adminMenu())]);
  return { text: lines.join("\n"), markup: { inline_keyboard: rows } };
}

export function productAdminView(p: ProductView): View {
  const e = (field: string, label: string) => btn.callback(label, cb.adminProductEdit(p.id, field));
  const rows: InlineKeyboardButton[][] = [
    [e("name", "✏️ Назва"), e("setNumber", "🔢 Номер"), e("theme", "🏷 Тематика")],
    [e("pieces", "🧩 Деталі"), e("ageMin", "👶 Вік"), e("price", "💰 Ціна")],
    [e("condition", "📦 Стан"), e("boxState", "🎁 Коробка"), e("completeness", "✅ Комплект")],
    [e("conditionNote", "📝 Примітка"), e("image", "🖼 Фото"), e("description", "📄 Опис")],
    [e("lowStockThreshold", "⚠️ Поріг «мало»")],
    [
      btn.callback("➕ Надійшло на склад", cb.adminProductStock(p.id, "add")),
      btn.callback("➖ Списати", cb.adminProductStock(p.id, "sub")),
    ],
    [
      btn.callback("📜 Історія змін", cb.adminProductHistory(p.id)),
      p.status === "ACTIVE"
        ? btn.callback("🗄 Архівувати", cb.adminProductArchive(p.id))
        : btn.callback("♻️ Відновити", cb.adminProductRestore(p.id)),
    ],
    [btn.callback("⬅️ До залишків", cb.adminProducts(p.status === "ACTIVE" ? "active" : "archived", 1))],
  ];
  return { text: adminProductCard(p), markup: { inline_keyboard: rows } };
}

const FIELD_LABELS: Record<string, string> = {
  created: "створено",
  name: "назва",
  setNumber: "номер набору",
  theme: "тематика",
  pieces: "деталей",
  ageMin: "вік",
  price: "ціна",
  condition: "стан",
  boxState: "коробка",
  completeness: "комплектність",
  conditionNote: "примітка",
  imageUrl: "фото (URL)",
  telegramFileId: "фото",
  description: "опис",
  lowStockThreshold: "поріг «мало»",
  status: "статус",
};

const MOVEMENT_LABELS: Record<string, string> = {
  INITIAL: "початковий залишок",
  RESTOCK: "надходження",
  ADJUSTMENT: "коригування",
  ORDER_RESERVE: "резерв",
  ORDER_RELEASE: "зняття резерву",
  ORDER_SHIP: "відвантаження",
  RETURN_RESTOCK: "повернення на склад",
};

export async function productHistoryView(s: Services, p: ProductView): Promise<View> {
  const { changes, movements } = await s.products.history(p.id, 15);
  const tz = s.config.shop.timezone;
  const events = [
    ...changes.map((c) => ({
      at: c.createdAt,
      line: `✏️ ${FIELD_LABELS[c.field] ?? c.field}: ${escapeHtml(truncate(c.oldValue ?? "—", 30))} → ${escapeHtml(
        truncate(c.newValue ?? "—", 30),
      )}`,
    })),
    ...movements.map((m) => ({
      at: m.createdAt,
      line: `📦 ${MOVEMENT_LABELS[m.type] ?? m.type}: склад ${m.onHandDelta >= 0 ? "+" : ""}${m.onHandDelta}, резерв ${
        m.reservedDelta >= 0 ? "+" : ""
      }${m.reservedDelta} → ${m.onHandAfter}/${m.reservedAfter}${m.orderId ? ` (№${m.orderId})` : ""}${
        m.note && !m.orderId ? ` — ${escapeHtml(truncate(m.note, 40))}` : ""
      }`,
    })),
  ]
    .sort((a, b) => b.at.getTime() - a.at.getTime())
    .slice(0, 25);
  const text = [
    `📜 <b>Історія: ${escapeHtml(productTitle(p))}</b>`,
    `<i>склад/резерв після операції</i>`,
    "",
    ...(events.length ? events.map((e) => `${formatDateTime(e.at, tz)} ${e.line}`) : ["Історія порожня."]),
  ].join("\n");
  return { text, markup: { inline_keyboard: [[btn.callback("⬅️ До товару", cb.adminProduct(p.id))]] } };
}

export async function customerListView(s: Services, page: number): Promise<View> {
  const { items, total } = await s.customers.list(ADMIN_PAGE_SIZE, (page - 1) * ADMIN_PAGE_SIZE);
  const pages = Math.max(1, Math.ceil(total / ADMIN_PAGE_SIZE));
  const tz = s.config.shop.timezone;
  const lines = [`👥 <b>Покупці</b> — ${total}`, ""];
  for (const c of items) {
    const name = c.fullName ?? [c.firstName, c.lastName].filter(Boolean).join(" ") ?? "";
    lines.push(
      `<code>${c.id}</code> ${escapeHtml(truncate(name || "Без імені", 28))}${c.username ? ` @${escapeHtml(c.username)}` : ""} · замовлень: ${
        c._count.orders
      } · ${formatMoney(c.totalSpent)}${c.lastOrderAt ? ` · ост. ${formatDate(c.lastOrderAt, tz)}` : ""}${
        c.isBlocked ? " · 🚫 заблокував бота" : ""
      }`,
    );
  }
  const rows: InlineKeyboardButton[][] = chunk(
    items.map((c) => btn.callback(`👤 ${truncate(c.fullName ?? c.firstName ?? String(c.id), 16)}`, cb.adminCustomer(c.id))),
    2,
  );
  const nav: InlineKeyboardButton[] = [];
  if (page > 1) nav.push(btn.callback("⬅️", cb.adminCustomers(page - 1)));
  if (pages > 1) nav.push(btn.callback(`${page}/${pages}`, cb.adminCustomers(page)));
  if (page < pages) nav.push(btn.callback("➡️", cb.adminCustomers(page + 1)));
  if (nav.length) rows.push(nav);
  rows.push([btn.callback("⬅️ Меню", cb.adminMenu())]);
  return { text: lines.join("\n"), markup: { inline_keyboard: rows } };
}

export async function customerView(s: Services, customerId: number): Promise<View | null> {
  const profile = await s.customers.profile(customerId);
  if (!profile) return null;
  const c = profile.customer;
  const tz = s.config.shop.timezone;
  const orders = await s.orders.customerOrders(customerId, 10);
  const text = [
    `👤 <b>${escapeHtml(c.fullName ?? ([c.firstName, c.lastName].filter(Boolean).join(" ") || "Без імені"))}</b>`,
    `Telegram ID: <code>${c.telegramId}</code>${c.username ? ` · @${escapeHtml(c.username)}` : ""}`,
    `Телефон: ${c.phone ? escapeHtml(c.phone) : "—"}`,
    `Доставка (остання): ${c.city ? `${escapeHtml(c.city)}, ${escapeHtml(c.deliveryPoint ?? "")}` : "—"}`,
    `Замовлень: ${profile.ordersCount} (доставлено: ${profile.completedCount})`,
    `Сума завершених покупок: <b>${formatMoney(c.totalSpent)}</b>`,
    `Останнє замовлення: ${c.lastOrderAt ? formatDateTime(c.lastOrderAt, tz) : "—"}`,
    `З нами з: ${formatDate(c.createdAt, tz)}`,
    c.marketingOptOut ? "📵 Відписаний від розсилок" : "",
    c.isBlocked ? "🚫 Заблокував бота" : "",
    c.anonymizedAt ? "🔐 Дані видалено на вимогу покупця" : "",
    "",
    "<b>Купував:</b>",
    ...(profile.purchasedSets.length
      ? profile.purchasedSets.map((p) => `• ${escapeHtml(p.title)} — ${p.quantity} шт. (ост. №${p.lastOrderId})`)
      : ["—"]),
  ]
    .filter((l, i, arr) => l !== "" || arr[i - 1] !== "")
    .join("\n");
  const rows: InlineKeyboardButton[][] = chunk(
    orders.map((o) => btn.callback(`${ORDER_STATUS_EMOJI[o.status]} №${o.id}`, cb.adminOrder(o.id))),
    3,
  );
  rows.push([btn.callback("⬅️ До покупців", cb.adminCustomers(1))]);
  return { text, markup: { inline_keyboard: rows } };
}

export function statsView(stats: ShopStats): View {
  const statusLines = (Object.keys(ORDER_STATUS_LABELS) as OrderStatus[])
    .filter((st) => stats.byStatus[st])
    .map((st) => `${ORDER_STATUS_EMOJI[st]} ${ORDER_STATUS_LABELS[st]}: ${stats.byStatus[st]}`);
  const text = [
    "📊 <b>Статистика магазину</b>",
    "",
    `Сьогодні: ${stats.today.orders} замовл. на ${formatMoney(stats.today.revenue)}`,
    `7 днів: ${stats.week.orders} замовл. на ${formatMoney(stats.week.revenue)}`,
    `30 днів: ${stats.month.orders} замовл. на ${formatMoney(stats.month.revenue)}`,
    `<i>(без скасованих)</i>`,
    `Доставлено всього на суму: <b>${formatMoney(stats.deliveredRevenue)}</b>`,
    "",
    "<b>Замовлення за статусами:</b>",
    ...(statusLines.length ? statusLines : ["—"]),
    "",
    `👥 Покупців: ${stats.customersTotal} (з замовленнями: ${stats.customersWithOrders})`,
    `🧱 Активних товарів: ${stats.activeProducts}`,
    `📦 Одиниць на складі: ${stats.unitsOnHand}, у резерві: ${stats.unitsReserved}`,
    `⚠️ Закінчуються: ${stats.lowStock} · ❌ немає в наявності: ${stats.outOfStock}`,
    "",
    "<b>Топ-5 за 30 днів:</b>",
    ...(stats.topProducts.length
      ? stats.topProducts.map(
          (t, i) =>
            `${i + 1}. ${escapeHtml(productTitle({ theme: t.theme, setNumber: t.setNumber, name: t.name }))} — ${t.quantity} шт., ${formatMoney(t.revenue)}`,
        )
      : ["—"]),
  ].join("\n");
  return {
    text,
    markup: {
      inline_keyboard: [[btn.callback("🔄 Оновити", cb.adminStats()), btn.callback("⬅️ Меню", cb.adminMenu())]],
    },
  };
}

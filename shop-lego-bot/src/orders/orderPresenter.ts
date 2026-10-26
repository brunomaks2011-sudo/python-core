import type { OrderStatus, PaymentMethod } from "../generated/prisma/client.js";
import { productTitle } from "../catalog/productPresenter.js";
import { escapeHtml, formatDateTime, formatMoney, formatSets } from "../lib/format.js";
import { maskPhone } from "../lib/logger.js";
import {
  ORDER_STATUS_EMOJI,
  ORDER_STATUS_LABELS,
  PAYMENT_METHOD_LABELS,
  isPrepayment,
  statusLabel,
} from "./orderStatus.js";
import type { OrderFull, OrderWithHistory } from "./types.js";

export interface ShopTexts {
  contact?: string;
  paymentDetails: string;
  timezone: string;
}

type ItemLike = OrderFull["items"][number];

function itemTitle(item: ItemLike): string {
  return productTitle({ theme: item.theme, setNumber: item.setNumber, name: item.productName });
}

function itemsBlock(order: OrderFull): string {
  return order.items
    .map(
      (i) =>
        `• ${escapeHtml(itemTitle(i))}${i.condition === "USED" ? " (вживаний)" : ""}\n` +
        `   ${i.quantity} × ${formatMoney(i.unitPrice)} = <b>${formatMoney(i.lineTotal)}</b>`,
    )
    .join("\n");
}

function deliveryLine(order: Pick<OrderFull, "city" | "deliveryPoint">): string {
  return `${escapeHtml(order.city)}, ${escapeHtml(order.deliveryPoint)}`;
}

/** Підтвердження покупцю одразу після оформлення. Статус — фактичний зі збереженого замовлення. */
export function customerOrderCreatedText(order: OrderFull, shop: ShopTexts): string {
  const single = order.items.length === 1 ? order.items[0] : undefined;
  const lines = ["Дякуємо за замовлення! 🎉", "", `Номер замовлення: <b>№${order.id}</b>.`, ""];
  if (single) {
    lines.push(`Товар: ${escapeHtml(itemTitle(single))}.`);
    lines.push(`Кількість: ${formatSets(single.quantity)}.`);
  } else {
    lines.push(itemsBlock(order));
  }
  lines.push(`Вартість: <b>${formatMoney(order.totalAmount)}</b>.`);
  lines.push("");
  lines.push(`Доставка: ${deliveryLine(order)}.`);
  lines.push(`Оплата: ${PAYMENT_METHOD_LABELS[order.paymentMethod]}.`);
  lines.push("");
  lines.push(`Статус: ${ORDER_STATUS_LABELS[order.status]}.`);
  lines.push("");
  if (order.status === "NEW" || order.status === "AWAITING_CONFIRMATION") {
    lines.push("Ми повідомимо вас, коли замовлення буде підтверджено.");
  }
  if (isPrepayment(order.paymentMethod)) {
    lines.push("Реквізити для оплати надішлемо після підтвердження замовлення магазином.");
  }
  lines.push("Переглянути замовлення можна командою /myorders.");
  return lines.join("\n");
}

/** Сповіщення власнику про нове замовлення. */
export function adminOrderCreatedText(
  order: OrderFull,
  stock: Array<{ productId: number; onHand: number; reserved: number; available: number }>,
  timezone: string,
): string {
  const c = order.customer;
  const username = c.username ? ` (@${escapeHtml(c.username)})` : "";
  const lines = [
    `🆕 <b>Нове замовлення №${order.id}</b>`,
    `${formatDateTime(order.createdAt, timezone)}`,
    "",
    `👤 ${escapeHtml(order.fullName)}${username}, ID <code>${c.telegramId}</code>`,
    `📞 ${escapeHtml(order.phone)}`,
    `📍 ${deliveryLine(order)}`,
    `💳 ${PAYMENT_METHOD_LABELS[order.paymentMethod]}`,
    "",
    itemsBlock(order),
    `Разом: <b>${formatMoney(order.totalAmount)}</b>`,
    "",
    "Залишки після резерву:",
    ...order.items.map((i) => {
      const s = stock.find((x) => x.productId === i.productId);
      return s
        ? `• ${escapeHtml(i.setNumber ?? i.productName)}: доступно ${s.available} (на складі ${s.onHand}, у резерві ${s.reserved})`
        : `• ${escapeHtml(i.setNumber ?? i.productName)}`;
    }),
  ];
  return lines.join("\n");
}

const STATUS_MESSAGES: Partial<Record<OrderStatus, string>> = {
  CONFIRMED: "✅ Ваше замовлення №{id} підтверджено магазином!",
  PAID: "💳 Оплату замовлення №{id} отримано. Дякуємо!",
  PACKING: "📦 Замовлення №{id} комплектується.",
  SHIPPED: "🚚 Замовлення №{id} відправлено!",
  DELIVERED: "🎉 Замовлення №{id} доставлено. Дякуємо за покупку — будемо раді бачити вас знову!",
  CANCELED: "❌ Замовлення №{id} скасовано.",
  RETURNED: "↩️ Для замовлення №{id} оформлено повернення.",
};

/** Повідомлення покупцю про зміну статусу; null — сповіщення не потрібне. */
export function customerStatusText(
  order: OrderFull,
  status: OrderStatus,
  shop: ShopTexts,
  note?: string | null,
): string | null {
  const template = STATUS_MESSAGES[status];
  if (!template) return null;
  const lines = [template.replace("{id}", String(order.id))];
  if (status === "CONFIRMED" && isPrepayment(order.paymentMethod)) {
    lines.push("");
    lines.push(`До сплати: <b>${formatMoney(order.totalAmount)}</b>.`);
    if (shop.paymentDetails) {
      lines.push(`Реквізити для оплати:\n${escapeHtml(shop.paymentDetails)}`);
      lines.push(`У призначенні платежу вкажіть: «Замовлення №${order.id}».`);
    } else {
      lines.push("Реквізити для оплати надішле менеджер магазину.");
    }
  }
  if (status === "SHIPPED" && order.trackingNumber) {
    lines.push(`Номер відправлення (ТТН): <code>${escapeHtml(order.trackingNumber)}</code>`);
  }
  if (note) lines.push(`Коментар магазину: ${escapeHtml(note)}`);
  if (status === "CANCELED" || status === "RETURNED") {
    lines.push(
      shop.contact
        ? `Якщо маєте запитання — напишіть продавцю: ${escapeHtml(shop.contact)}`
        : "Якщо маєте запитання — напишіть нам у цьому чаті.",
    );
  }
  lines.push("");
  lines.push(`Поточний статус: ${ORDER_STATUS_LABELS[status]}.`);
  return lines.join("\n");
}

/** Детальна інформація про замовлення для покупця. */
export function customerOrderDetailsText(order: OrderFull, timezone: string): string {
  return [
    `${ORDER_STATUS_EMOJI[order.status]} <b>Замовлення №${order.id}</b> від ${formatDateTime(order.createdAt, timezone)}`,
    "",
    itemsBlock(order),
    `Разом: <b>${formatMoney(order.totalAmount)}</b>`,
    "",
    `Доставка: ${deliveryLine(order)}`,
    `Оплата: ${PAYMENT_METHOD_LABELS[order.paymentMethod]}`,
    order.trackingNumber ? `ТТН: <code>${escapeHtml(order.trackingNumber)}</code>` : "",
    `Статус: <b>${ORDER_STATUS_LABELS[order.status]}</b>`,
  ]
    .filter((l) => l !== "")
    .join("\n");
}

export function orderShortLine(order: OrderFull, timezone: string): string {
  const first = order.items[0];
  const what = first
    ? `${escapeHtml(first.setNumber ? `${first.setNumber}` : first.productName)}${
        order.items.length > 1 ? ` +${order.items.length - 1}` : ""
      }`
    : "—";
  return `${ORDER_STATUS_EMOJI[order.status]} №${order.id} · ${formatDateTime(order.createdAt, timezone)} · ${what} · ${formatMoney(order.totalAmount)} · ${ORDER_STATUS_LABELS[order.status]}`;
}

/** Повна картка замовлення для адміністратора. */
export function adminOrderDetailsText(order: OrderWithHistory, timezone: string): string {
  const c = order.customer;
  const lines = [
    `${ORDER_STATUS_EMOJI[order.status]} <b>Замовлення №${order.id}</b> — ${statusLabel(order.status)}`,
    `Створено: ${formatDateTime(order.createdAt, timezone)}`,
    `Склад: ${stockStateLabel(order.stockState)}`,
    "",
    `👤 ${escapeHtml(order.fullName)}${c.username ? ` (@${escapeHtml(c.username)})` : ""}, ID <code>${c.telegramId}</code>`,
    `📞 ${escapeHtml(order.phone)}`,
    `📍 ${deliveryLine(order)}`,
    `💳 ${PAYMENT_METHOD_LABELS[order.paymentMethod]}`,
    order.trackingNumber ? `🚚 ТТН: <code>${escapeHtml(order.trackingNumber)}</code>` : "",
    "",
    itemsBlock(order),
    `Разом: <b>${formatMoney(order.totalAmount)}</b>`,
    "",
    "<b>Історія:</b>",
    ...order.history.map(
      (h) =>
        `• ${formatDateTime(h.createdAt, timezone)} — ${h.fromStatus ? `${ORDER_STATUS_LABELS[h.fromStatus]} → ` : ""}${
          ORDER_STATUS_LABELS[h.toStatus]
        } (${h.actorType === "ADMIN" ? "адмін" : h.actorType === "CUSTOMER" ? "покупець" : "система"})${
          h.note ? `: ${escapeHtml(h.note)}` : ""
        }`,
    ),
  ];
  return lines.filter((l, i, arr) => !(l === "" && arr[i - 1] === "")).join("\n");
}

export function stockStateLabel(state: OrderFull["stockState"]): string {
  switch (state) {
    case "RESERVED":
      return "товар зарезервовано";
    case "RELEASED":
      return "резерв знято";
    case "SHIPPED":
      return "товар списано (відправлено)";
    case "RESTOCKED":
      return "товар повернуто на склад";
    case "WRITTEN_OFF":
      return "повернення без повернення на склад";
  }
}

export function paymentLabel(method: PaymentMethod): string {
  return PAYMENT_METHOD_LABELS[method];
}

export function maskedCustomerLine(c: OrderFull["customer"]): string {
  return `${escapeHtml(c.fullName ?? c.firstName ?? "Без імені")}${c.username ? ` (@${escapeHtml(c.username)})` : ""} · ${maskPhone(c.phone)}`;
}

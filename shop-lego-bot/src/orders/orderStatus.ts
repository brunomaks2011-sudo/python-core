import type { OrderStatus, PaymentMethod } from "../generated/prisma/client.js";

export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  NEW: "нове",
  AWAITING_CONFIRMATION: "очікує підтвердження магазину",
  CONFIRMED: "підтверджене",
  PAID: "оплачене",
  PACKING: "комплектується",
  SHIPPED: "відправлене",
  DELIVERED: "доставлене",
  CANCELED: "скасоване",
  RETURNED: "повернення",
};

export const ORDER_STATUS_EMOJI: Record<OrderStatus, string> = {
  NEW: "🆕",
  AWAITING_CONFIRMATION: "⏳",
  CONFIRMED: "✅",
  PAID: "💳",
  PACKING: "📦",
  SHIPPED: "🚚",
  DELIVERED: "🎉",
  CANCELED: "❌",
  RETURNED: "↩️",
};

/** Назви кнопок зміни статусу в адмін-панелі. */
export const ORDER_STATUS_ACTIONS: Record<OrderStatus, string> = {
  NEW: "🆕 Нове",
  AWAITING_CONFIRMATION: "⏳ Очікує підтвердження",
  CONFIRMED: "✅ Підтвердити",
  PAID: "💳 Оплачене",
  PACKING: "📦 Комплектується",
  SHIPPED: "🚚 Відправлене",
  DELIVERED: "🎉 Доставлене",
  CANCELED: "❌ Скасувати",
  RETURNED: "↩️ Повернення",
};

export function statusLabel(status: OrderStatus): string {
  const label = ORDER_STATUS_LABELS[status];
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/**
 * Дозволені переходи статусів. Скасувати можна лише до відправлення;
 * після відправлення — тільки оформити повернення.
 */
export const ORDER_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  NEW: ["AWAITING_CONFIRMATION", "CONFIRMED", "CANCELED"],
  AWAITING_CONFIRMATION: ["CONFIRMED", "CANCELED"],
  CONFIRMED: ["PAID", "PACKING", "SHIPPED", "CANCELED"],
  PAID: ["PACKING", "SHIPPED", "CANCELED"],
  PACKING: ["PAID", "SHIPPED", "CANCELED"],
  SHIPPED: ["DELIVERED", "RETURNED"],
  DELIVERED: ["RETURNED"],
  CANCELED: [],
  RETURNED: [],
};

export function canTransition(from: OrderStatus, to: OrderStatus): boolean {
  return ORDER_TRANSITIONS[from].includes(to);
}

/** Статуси, у яких замовлення ще в роботі (покупець не може видалити свої дані). */
export const ACTIVE_ORDER_STATUSES: OrderStatus[] = [
  "NEW",
  "AWAITING_CONFIRMATION",
  "CONFIRMED",
  "PAID",
  "PACKING",
  "SHIPPED",
];

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  CASH_ON_DELIVERY: "Накладений платіж (оплата при отриманні)",
  CARD_TRANSFER: "Переказ на картку",
  BANK_TRANSFER: "Оплата за реквізитами (IBAN)",
};

export const PAYMENT_METHOD_BUTTONS: Record<PaymentMethod, string> = {
  CASH_ON_DELIVERY: "💵 При отриманні",
  CARD_TRANSFER: "💳 Переказ на картку",
  BANK_TRANSFER: "🏦 За реквізитами (IBAN)",
};

export function isPrepayment(method: PaymentMethod): boolean {
  return method === "CARD_TRANSFER" || method === "BANK_TRANSFER";
}

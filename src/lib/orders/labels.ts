import type { OrderStatus, PaymentStatus } from "@prisma/client";

export const ORDER_STATUS: Record<OrderStatus, { label: string; color: string }> = {
  NEW: { label: "Нове", color: "bg-sky-100 text-sky-800" },
  PAID: { label: "Оплачене", color: "bg-emerald-100 text-emerald-800" },
  SHIPPED: { label: "Відправлене", color: "bg-violet-100 text-violet-800" },
  DELIVERED: { label: "Доставлене", color: "bg-ink/10 text-ink" },
  CANCELLED: { label: "Скасоване", color: "bg-tomato-500/10 text-tomato-600" },
};

export const PAYMENT_STATUS: Record<PaymentStatus, { label: string; color: string }> = {
  PENDING: { label: "Очікує оплати", color: "bg-brand-100 text-brand-600" },
  PAID: { label: "Оплачено", color: "bg-emerald-100 text-emerald-800" },
  FAILED: { label: "Помилка оплати", color: "bg-tomato-500/10 text-tomato-600" },
  REFUNDED: { label: "Повернено", color: "bg-ink/10 text-ink" },
};

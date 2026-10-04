import "server-only";
import { randomBytes } from "node:crypto";
import type { Order } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { absoluteUrl, siteConfig } from "@/config/site";
import { getOnlinePaymentProvider, type PaymentCallback } from "@/lib/payments";

/** Створює нову спробу онлайн-оплати і повертає адресу сторінки оплати. */
export async function startOnlinePayment(order: Pick<Order, "id" | "number" | "accessToken" | "total" | "paymentStatus">) {
  const provider = getOnlinePaymentProvider();
  if (!provider) throw new Error("Онлайн-оплата не налаштована");
  if (order.paymentStatus === "PAID") throw new Error("Замовлення вже оплачене");

  // Новий order_id на кожну спробу: LiqPay не дозволяє повторно використовувати ідентифікатор
  const externalId = `${order.number}-${randomBytes(3).toString("hex")}`;
  await prisma.order.update({
    where: { id: order.id },
    data: { paymentExternalId: externalId, paymentProvider: provider.id, paymentStatus: "PENDING" },
  });
  const qs = new URLSearchParams({ order: order.number, t: order.accessToken });
  return provider.createPayment({
    orderNumber: order.number,
    externalId,
    amount: order.total,
    currency: "UAH",
    description: `Оплата замовлення №${order.number} у магазині «${siteConfig.name}»`,
    resultUrl: absoluteUrl(`/payment/return?${qs}`),
    serverUrl: absoluteUrl(`/api/payments/${provider.id}/callback`),
  });
}

export type ApplyResult = "updated" | "ignored" | "not_found" | "amount_mismatch";

/**
 * Застосовує підтверджений (з перевіреним підписом) результат оплати до замовлення.
 * Ідемпотентно: повторні callback не змінюють уже оплачене замовлення.
 */
export async function applyPaymentResult(cb: PaymentCallback): Promise<ApplyResult> {
  const order = await prisma.order.findUnique({ where: { paymentExternalId: cb.externalId } });
  if (!order) return "not_found";

  if (cb.status === "paid") {
    if (cb.amount !== order.total || cb.currency !== "UAH") {
      console.error(`[payment] сума не збігається для ${order.number}: ${cb.amount} ${cb.currency} ≠ ${order.total}`);
      return "amount_mismatch";
    }
    if (order.paymentStatus === "PAID") return "ignored";
    await prisma.order.update({
      where: { id: order.id },
      data: {
        paymentStatus: "PAID",
        paidAt: new Date(),
        status: order.status === "NEW" ? "PAID" : order.status,
      },
    });
    return "updated";
  }
  if (cb.status === "failed") {
    if (order.paymentStatus === "PAID") return "ignored";
    await prisma.order.update({ where: { id: order.id }, data: { paymentStatus: "FAILED" } });
    return "updated";
  }
  if (cb.status === "refunded") {
    await prisma.order.update({ where: { id: order.id }, data: { paymentStatus: "REFUNDED" } });
    return "updated";
  }
  return "ignored";
}

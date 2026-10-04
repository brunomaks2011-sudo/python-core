"use server";

import { redirect } from "next/navigation";
import { getAccessibleOrder } from "@/lib/orders/access";
import { startOnlinePayment } from "@/lib/orders/payment";

/** Повторна спроба онлайн-оплати (після помилки або якщо покупець закрив сторінку). */
export async function retryPayment(formData: FormData) {
  const number = String(formData.get("number") ?? "");
  const token = String(formData.get("t") ?? "");
  const order = await getAccessibleOrder(number, token);
  if (!order || order.paymentMethod !== "LIQPAY" || order.paymentStatus === "PAID" || order.status === "CANCELLED") {
    redirect("/");
  }
  const { url } = await startOnlinePayment(order);
  redirect(url);
}

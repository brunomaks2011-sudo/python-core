import { redirect } from "next/navigation";
import { getAccessibleOrder } from "@/lib/orders/access";
import { applyPaymentResult } from "@/lib/orders/payment";
import { getPaymentProvider } from "@/lib/payments";

export const metadata = { robots: { index: false } };

type Props = { searchParams: Promise<{ order?: string; t?: string }> };

/**
 * Сюди LiqPay повертає покупця (result_url). Callback може прийти із затримкою,
 * тому за потреби активно запитуємо статус платежу (запит підписаний приватним ключем).
 */
export default async function PaymentReturnPage({ searchParams }: Props) {
  const { order: number = "", t = "" } = await searchParams;
  let order = await getAccessibleOrder(number, t);
  if (!order) redirect("/");

  if (order.paymentStatus !== "PAID" && order.paymentExternalId && order.paymentProvider) {
    const provider = getPaymentProvider(order.paymentProvider);
    const status = await provider?.checkStatus?.(order.paymentExternalId);
    if (status && status.externalId === order.paymentExternalId) {
      await applyPaymentResult(status);
      order = (await getAccessibleOrder(number, t))!;
    }
  }

  const qs = `order=${encodeURIComponent(order.number)}&t=${encodeURIComponent(order.accessToken)}`;
  if (order.paymentStatus === "PAID") redirect(`/payment/success?${qs}`);
  if (order.paymentStatus === "FAILED") redirect(`/payment/failure?${qs}`);
  // Платіж ще обробляється
  redirect(`/order/${order.number}?t=${encodeURIComponent(order.accessToken)}`);
}

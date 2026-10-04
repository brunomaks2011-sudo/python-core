import Link from "next/link";
import { notFound } from "next/navigation";
import { getAccessibleOrder } from "@/lib/orders/access";
import { OrderDetails } from "@/components/orders/OrderDetails";

export const metadata = { title: "Оплата успішна", robots: { index: false } };

export default async function PaymentSuccessPage({ searchParams }: { searchParams: Promise<{ order?: string; t?: string }> }) {
  const { order: number = "", t } = await searchParams;
  const order = await getAccessibleOrder(number, t);
  if (!order) notFound();
  const paid = order.paymentStatus === "PAID";
  return (
    <div className="container-page max-w-3xl py-10">
      <div className="mb-6 text-center">
        <p className="text-6xl" aria-hidden>{paid ? "✅" : "⏳"}</p>
        <h1 className="mt-3 text-3xl font-black">{paid ? "Оплата пройшла успішно!" : "Очікуємо підтвердження оплати"}</h1>
        <p className="mt-2 text-ink/70">
          {paid
            ? "Дякуємо за покупку! Ми вже збираємо ваше замовлення і повідомимо номер ТТН після відправлення."
            : "Банк ще обробляє платіж. Статус оновиться автоматично — оновіть сторінку за хвилину."}
        </p>
      </div>
      <OrderDetails order={order} />
      <div className="mt-6 text-center">
        <Link href="/catalog" className="btn-primary">Продовжити покупки</Link>
      </div>
    </div>
  );
}

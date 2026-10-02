import Link from "next/link";
import { notFound } from "next/navigation";
import { getAccessibleOrder } from "@/lib/orders/access";
import { retryPayment } from "@/app/actions/payment";

export const metadata = { title: "Помилка оплати", robots: { index: false } };

export default async function PaymentFailurePage({ searchParams }: { searchParams: Promise<{ order?: string; t?: string }> }) {
  const { order: number = "", t } = await searchParams;
  const order = await getAccessibleOrder(number, t);
  if (!order) notFound();
  return (
    <div className="container-page max-w-xl py-16 text-center">
      <p className="text-6xl" aria-hidden>😕</p>
      <h1 className="mt-3 text-3xl font-black">Оплата не пройшла</h1>
      <p className="mt-2 text-ink/70">
        Платіж за замовлення №{order.number} було відхилено або скасовано. Кошти не списано.
        Спробуйте ще раз або оберіть іншу картку.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        {order.paymentStatus !== "PAID" && order.status !== "CANCELLED" && (
          <form action={retryPayment}>
            <input type="hidden" name="number" value={order.number} />
            <input type="hidden" name="t" value={order.accessToken} />
            <button className="btn-primary">Спробувати ще раз</button>
          </form>
        )}
        <Link href={`/order/${order.number}?t=${order.accessToken}`} className="btn-ghost">Деталі замовлення</Link>
      </div>
      <p className="mt-6 text-sm text-ink/60">Якщо проблема повторюється — зателефонуйте нам, і ми допоможемо оформити оплату при отриманні.</p>
    </div>
  );
}

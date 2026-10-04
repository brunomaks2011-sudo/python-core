import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getAccessibleOrder } from "@/lib/orders/access";
import { OrderDetails } from "@/components/orders/OrderDetails";
import { retryPayment } from "@/app/actions/payment";
import { getOnlinePaymentProvider } from "@/lib/payments";

export const metadata: Metadata = { title: "Замовлення", robots: { index: false } };

type Props = { params: Promise<{ number: string }>; searchParams: Promise<{ t?: string; new?: string; payment?: string }> };

export default async function OrderPage({ params, searchParams }: Props) {
  const { number } = await params;
  const sp = await searchParams;
  const order = await getAccessibleOrder(number, sp.t);
  if (!order) notFound();

  const canPay =
    order.paymentMethod === "LIQPAY" && order.paymentStatus !== "PAID" && order.status !== "CANCELLED" && !!getOnlinePaymentProvider();

  return (
    <div className="container-page max-w-3xl py-10">
      {sp.new && (
        <div className="mb-6 text-center">
          <p className="text-5xl" aria-hidden>🎉</p>
          <h1 className="mt-2 text-3xl font-black">Дякуємо! Замовлення прийнято</h1>
          <p className="mt-2 text-ink/70">Ми надіслали підтвердження на {order.contactEmail}. Менеджер зв&apos;яжеться з вами найближчим часом.</p>
        </div>
      )}
      {!sp.new && <h1 className="mb-6 text-3xl font-black">Статус замовлення</h1>}
      {sp.payment === "error" && (
        <p className="mb-4 rounded-xl bg-tomato-500/10 p-3 text-sm font-bold text-tomato-600">
          Замовлення створено, але не вдалося перейти до оплати. Спробуйте ще раз нижче.
        </p>
      )}
      <OrderDetails order={order} />
      {canPay && (
        <form action={retryPayment} className="mt-6 text-center">
          <input type="hidden" name="number" value={order.number} />
          <input type="hidden" name="t" value={order.accessToken} />
          <button className="btn-primary px-8 py-3 text-base">Оплатити онлайн</button>
        </form>
      )}
      <p className="mt-6 text-center text-sm text-ink/60">
        Збережіть це посилання, щоб відстежувати замовлення. <Link href="/catalog" className="font-bold text-sky-brand">Продовжити покупки →</Link>
      </p>
    </div>
  );
}

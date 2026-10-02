import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { requireUser } from "@/lib/auth-guards";
import { formatUAH } from "@/lib/money";
import { formatDate } from "@/lib/utils";
import { OrderStatusBadge, PaymentStatusBadge } from "@/components/orders/StatusBadge";
import { DELIVERY_METHODS } from "@/lib/delivery/methods";

export default async function AccountOrdersPage() {
  const user = await requireUser("/account/orders");
  const orders = await prisma.order.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" },
    include: { _count: { select: { items: true } } },
    take: 100,
  });

  if (!orders.length) {
    return (
      <div className="card p-10 text-center">
        <p className="text-xl font-black">Замовлень поки немає</p>
        <Link href="/catalog" className="btn-primary mt-4">До каталогу</Link>
      </div>
    );
  }

  return (
    <ul className="space-y-3">
      {orders.map((o) => (
        <li key={o.id}>
          <Link href={`/order/${o.number}`} className="card flex flex-wrap items-center gap-x-6 gap-y-2 p-4 transition hover:shadow-md">
            <div className="min-w-40">
              <p className="font-black">№{o.number}</p>
              <p className="text-xs text-ink/50">{formatDate(o.createdAt)}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <OrderStatusBadge status={o.status} />
              <PaymentStatusBadge status={o.paymentStatus} cod={o.paymentMethod === "COD"} />
            </div>
            <p className="text-sm text-ink/60">{DELIVERY_METHODS[o.deliveryMethod].short}{o.trackingNumber && ` · ТТН ${o.trackingNumber}`}</p>
            <p className="ml-auto text-lg font-black">{formatUAH(o.total)}</p>
          </Link>
        </li>
      ))}
    </ul>
  );
}

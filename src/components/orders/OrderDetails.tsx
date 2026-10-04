import type { Order, OrderItem } from "@prisma/client";
import { formatUAH } from "@/lib/money";
import { formatDate } from "@/lib/utils";
import { DELIVERY_METHODS, describeDelivery } from "@/lib/delivery/methods";
import { OrderStatusBadge, PaymentStatusBadge } from "./StatusBadge";

export function OrderDetails({ order }: { order: Order & { items: OrderItem[] } }) {
  return (
    <div className="card p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-black">Замовлення №{order.number}</h2>
          <p className="text-sm text-ink/50">{formatDate(order.createdAt)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <OrderStatusBadge status={order.status} />
          <PaymentStatusBadge status={order.paymentStatus} cod={order.paymentMethod === "COD"} />
        </div>
      </div>
      <ul className="mt-4 divide-y divide-ink/5 text-sm">
        {order.items.map((i) => (
          <li key={i.id} className="flex justify-between gap-3 py-2">
            <span>{i.productName} <span className="text-ink/50">(арт. {i.productSku})</span> × {i.quantity}</span>
            <span className="whitespace-nowrap font-semibold">{formatUAH(i.unitPrice * i.quantity)}</span>
          </li>
        ))}
      </ul>
      <dl className="mt-4 space-y-1 border-t-2 border-dashed border-ink/10 pt-4 text-sm">
        <div className="flex justify-between"><dt>Товари</dt><dd>{formatUAH(order.itemsTotal)}</dd></div>
        <div className="flex justify-between"><dt>Доставка</dt><dd>{order.deliveryCost ? formatUAH(order.deliveryCost) : "безкоштовно"}</dd></div>
        <div className="flex justify-between text-lg font-black"><dt>Разом</dt><dd>{formatUAH(order.total)}</dd></div>
      </dl>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div className="rounded-xl bg-brand-50 p-3">
          <p className="text-xs font-bold text-ink/50">Доставка</p>
          <p className="font-semibold">{DELIVERY_METHODS[order.deliveryMethod].label}</p>
          <p>{describeDelivery(order.deliveryMethod, order.deliveryData)}</p>
          {order.trackingNumber && <p className="mt-1">ТТН: <span className="font-mono font-bold">{order.trackingNumber}</span></p>}
        </div>
        <div className="rounded-xl bg-brand-50 p-3">
          <p className="text-xs font-bold text-ink/50">Отримувач</p>
          <p className="font-semibold">{order.contactName}</p>
          <p>{order.contactPhone} · {order.contactEmail}</p>
        </div>
      </div>
    </div>
  );
}

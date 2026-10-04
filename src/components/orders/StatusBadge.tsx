import type { OrderStatus, PaymentStatus } from "@prisma/client";
import { ORDER_STATUS, PAYMENT_STATUS } from "@/lib/orders/labels";
import { cn } from "@/lib/utils";

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const s = ORDER_STATUS[status];
  return <span className={cn("inline-block rounded-full px-2.5 py-1 text-xs font-bold", s.color)}>{s.label}</span>;
}

export function PaymentStatusBadge({ status, cod }: { status: PaymentStatus; cod?: boolean }) {
  if (cod && status === "PENDING") {
    return <span className="inline-block rounded-full bg-ink/5 px-2.5 py-1 text-xs font-bold text-ink/70">Оплата при отриманні</span>;
  }
  const s = PAYMENT_STATUS[status];
  return <span className={cn("inline-block rounded-full px-2.5 py-1 text-xs font-bold", s.color)}>{s.label}</span>;
}

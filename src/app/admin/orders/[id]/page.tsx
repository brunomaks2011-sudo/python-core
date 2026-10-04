import Link from "next/link";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guards";
import { formatDate } from "@/lib/utils";
import { PageTitle, Panel } from "@/components/admin/ui";
import { OrderDetails } from "@/components/orders/OrderDetails";
import { OrderStatusForm } from "@/components/admin/OrderStatusForm";

export const metadata = { title: "Замовлення" };

export default async function AdminOrderPage({ params }: { params: Promise<{ id: string }> }) {
  await requireAdmin();
  const { id } = await params;
  const order = await prisma.order.findUnique({ where: { id }, include: { items: true, user: { select: { id: true, email: true } } } });
  if (!order) notFound();
  return (
    <>
      <PageTitle actions={<Link href="/admin/orders" className="btn-ghost">← До списку</Link>}>Замовлення №{order.number}</PageTitle>
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          <OrderDetails order={order} />
          {order.comment && <Panel title="Коментар покупця"><p className="whitespace-pre-line text-sm">{order.comment}</p></Panel>}
        </div>
        <div className="space-y-4">
          <Panel title="Керування">
            <OrderStatusForm id={order.id} status={order.status} trackingNumber={order.trackingNumber} />
          </Panel>
          <Panel title="Оплата">
            <dl className="space-y-1 text-sm">
              <div className="flex justify-between"><dt>Спосіб</dt><dd className="font-bold">{order.paymentMethod === "COD" ? "При отриманні" : "LiqPay"}</dd></div>
              {order.paymentExternalId && <div className="flex justify-between gap-2"><dt>ID платежу</dt><dd className="font-mono text-xs">{order.paymentExternalId}</dd></div>}
              {order.paidAt && <div className="flex justify-between"><dt>Оплачено</dt><dd>{formatDate(order.paidAt)}</dd></div>}
              <div className="flex justify-between"><dt>Акаунт</dt><dd>{order.user ? order.user.email : "гість"}</dd></div>
            </dl>
          </Panel>
        </div>
      </div>
    </>
  );
}

import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guards";
import { formatUAH } from "@/lib/money";
import { formatDate } from "@/lib/utils";
import { PageTitle, Panel, Table } from "@/components/admin/ui";
import { OrderStatusBadge, PaymentStatusBadge } from "@/components/orders/StatusBadge";

export const metadata = { title: "Дашборд" };

const LOW_STOCK = 5;

export default async function AdminDashboard() {
  await requireAdmin();
  const now = new Date();
  const monthAgo = new Date(now.getTime() - 30 * 24 * 3600 * 1000);

  // Виручка — оплачені замовлення (онлайн або накладений платіж після доставки), без скасованих
  const revenueWhere = { paymentStatus: "PAID" as const, status: { not: "CANCELLED" as const } };
  const [ordersTotal, ordersMonth, ordersNew, revenueAll, revenueMonth, lowStock, recent, productsCount, usersCount] =
    await Promise.all([
      prisma.order.count(),
      prisma.order.count({ where: { createdAt: { gte: monthAgo } } }),
      prisma.order.count({ where: { status: "NEW" } }),
      prisma.order.aggregate({ where: revenueWhere, _sum: { total: true } }),
      prisma.order.aggregate({ where: { ...revenueWhere, createdAt: { gte: monthAgo } }, _sum: { total: true } }),
      prisma.product.findMany({ where: { stock: { lte: LOW_STOCK }, isActive: true }, orderBy: { stock: "asc" }, take: 10 }),
      prisma.order.findMany({ orderBy: { createdAt: "desc" }, take: 8 }),
      prisma.product.count(),
      prisma.user.count(),
    ]);

  const stats = [
    { label: "Замовлень усього", value: ordersTotal, hint: `${ordersMonth} за 30 днів` },
    { label: "Нові (потребують обробки)", value: ordersNew, hint: "статус «Нове»", href: "/admin/orders?status=NEW" },
    { label: "Виручка за 30 днів", value: formatUAH(revenueMonth._sum.total ?? 0), hint: `усього ${formatUAH(revenueAll._sum.total ?? 0)}` },
    { label: "Товарів / користувачів", value: `${productsCount} / ${usersCount}`, hint: `${lowStock.length} закінчуються` },
  ];

  return (
    <>
      <PageTitle>Дашборд</PageTitle>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => {
          const body = (
            <>
              <p className="text-xs font-bold uppercase text-ink/50">{s.label}</p>
              <p className="mt-1 text-3xl font-black">{s.value}</p>
              <p className="mt-1 text-xs text-ink/50">{s.hint}</p>
            </>
          );
          return s.href ? (
            <Link key={s.label} href={s.href} className="rounded-2xl bg-white p-5 shadow-sm hover:shadow-md">{body}</Link>
          ) : (
            <div key={s.label} className="rounded-2xl bg-white p-5 shadow-sm">{body}</div>
          );
        })}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_380px]">
        <div>
          <h2 className="mb-3 text-lg font-black">Останні замовлення</h2>
          <Table>
            <thead><tr><th>№</th><th>Дата</th><th>Клієнт</th><th>Статус</th><th className="text-right">Сума</th></tr></thead>
            <tbody>
              {recent.map((o) => (
                <tr key={o.id}>
                  <td><Link className="font-bold text-sky-brand" href={`/admin/orders/${o.id}`}>{o.number}</Link></td>
                  <td className="whitespace-nowrap">{formatDate(o.createdAt)}</td>
                  <td>{o.contactName}</td>
                  <td className="space-x-1"><OrderStatusBadge status={o.status} /><PaymentStatusBadge status={o.paymentStatus} cod={o.paymentMethod === "COD"} /></td>
                  <td className="text-right font-bold">{formatUAH(o.total)}</td>
                </tr>
              ))}
              {recent.length === 0 && <tr><td colSpan={5} className="text-center text-ink/50">Замовлень ще немає</td></tr>}
            </tbody>
          </Table>
        </div>
        <Panel title={`Закінчуються (≤ ${LOW_STOCK} шт.)`}>
          <ul className="divide-y divide-ink/5 text-sm">
            {lowStock.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2 py-2">
                <Link href={`/admin/products/${p.id}`} className="hover:text-sky-brand">{p.name} <span className="text-ink/40">{p.sku}</span></Link>
                <span className={p.stock === 0 ? "font-black text-tomato-600" : "font-black text-brand-600"}>{p.stock} шт.</span>
              </li>
            ))}
            {lowStock.length === 0 && <li className="py-2 text-ink/50">Усі товари в достатній кількості 👍</li>}
          </ul>
        </Panel>
      </div>
    </>
  );
}

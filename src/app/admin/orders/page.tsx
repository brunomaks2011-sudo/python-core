import Link from "next/link";
import type { OrderStatus, Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guards";
import { formatUAH } from "@/lib/money";
import { formatDate } from "@/lib/utils";
import { PageTitle, Table } from "@/components/admin/ui";
import { Pagination } from "@/components/catalog/Pagination";
import { OrderStatusBadge, PaymentStatusBadge } from "@/components/orders/StatusBadge";
import { ORDER_STATUS } from "@/lib/orders/labels";
import { DELIVERY_METHODS } from "@/lib/delivery/methods";

export const metadata = { title: "Замовлення" };
const PER_PAGE = 25;

type Props = { searchParams: Promise<{ status?: string; from?: string; to?: string; q?: string; page?: string }> };

const isDate = (s?: string) => !!s && /^\d{4}-\d{2}-\d{2}$/.test(s);

export default async function AdminOrdersPage({ searchParams }: Props) {
  await requireAdmin();
  const sp = await searchParams;
  const status = sp.status && sp.status in ORDER_STATUS ? (sp.status as OrderStatus) : undefined;
  const q = (sp.q ?? "").trim().slice(0, 60);
  const page = Math.max(1, Number(sp.page) || 1);

  const createdAt: Prisma.DateTimeFilter = {};
  if (isDate(sp.from)) createdAt.gte = new Date(`${sp.from}T00:00:00+03:00`);
  if (isDate(sp.to)) createdAt.lte = new Date(`${sp.to}T23:59:59.999+03:00`);
  const where: Prisma.OrderWhereInput = {
    ...(status ? { status } : {}),
    ...(Object.keys(createdAt).length ? { createdAt } : {}),
    ...(q
      ? { OR: [{ number: { contains: q } }, { contactPhone: { contains: q } }, { contactEmail: { contains: q, mode: "insensitive" } }, { contactName: { contains: q, mode: "insensitive" } }] }
      : {}),
  };

  const [total, orders, counts] = await Promise.all([
    prisma.order.count({ where }),
    prisma.order.findMany({ where, orderBy: { createdAt: "desc" }, skip: (page - 1) * PER_PAGE, take: PER_PAGE }),
    prisma.order.groupBy({ by: ["status"], _count: true }),
  ]);
  const countOf = (s: OrderStatus) => counts.find((c) => c.status === s)?._count ?? 0;
  const params = (over: Record<string, string | undefined>) => {
    const p = new URLSearchParams();
    const merged = { status, from: sp.from, to: sp.to, q: q || undefined, ...over };
    for (const [k, v] of Object.entries(merged)) if (v) p.set(k, v);
    return `/admin/orders?${p}`;
  };

  return (
    <>
      <PageTitle>Замовлення ({total})</PageTitle>
      <div className="mb-4 flex flex-wrap gap-2 text-sm font-bold">
        <Link href={params({ status: undefined, page: undefined })} className={`rounded-full px-3 py-1.5 ${!status ? "bg-ink text-white" : "bg-white"}`}>Усі</Link>
        {(Object.keys(ORDER_STATUS) as OrderStatus[]).map((s) => (
          <Link key={s} href={params({ status: s, page: undefined })} className={`rounded-full px-3 py-1.5 ${status === s ? "bg-ink text-white" : "bg-white"}`}>
            {ORDER_STATUS[s].label} <span className="opacity-50">{countOf(s)}</span>
          </Link>
        ))}
      </div>
      <form className="mb-4 flex flex-wrap items-end gap-3 rounded-2xl bg-white p-4 shadow-sm">
        {status && <input type="hidden" name="status" value={status} />}
        <div><label className="label" htmlFor="o-from">Від</label><input id="o-from" type="date" name="from" defaultValue={sp.from} className="input" /></div>
        <div><label className="label" htmlFor="o-to">До</label><input id="o-to" type="date" name="to" defaultValue={sp.to} className="input" /></div>
        <div className="min-w-56 flex-1"><label className="label" htmlFor="o-q">Пошук</label><input id="o-q" name="q" defaultValue={q} placeholder="№, телефон, email, ім'я" className="input" /></div>
        <button className="btn-secondary">Фільтрувати</button>
        <Link href="/admin/orders" className="btn-ghost">Скинути</Link>
      </form>
      <Table>
        <thead><tr><th>№</th><th>Дата</th><th>Клієнт</th><th>Доставка</th><th>Статуси</th><th className="text-right">Сума</th></tr></thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td><Link href={`/admin/orders/${o.id}`} className="font-bold text-sky-brand">{o.number}</Link></td>
              <td className="whitespace-nowrap">{formatDate(o.createdAt)}</td>
              <td>{o.contactName}<p className="text-xs text-ink/50">{o.contactPhone}</p></td>
              <td>{DELIVERY_METHODS[o.deliveryMethod].short}{o.trackingNumber && <p className="font-mono text-xs">{o.trackingNumber}</p>}</td>
              <td className="space-x-1 whitespace-nowrap"><OrderStatusBadge status={o.status} /><PaymentStatusBadge status={o.paymentStatus} cod={o.paymentMethod === "COD"} /></td>
              <td className="text-right font-bold">{formatUAH(o.total)}</td>
            </tr>
          ))}
          {orders.length === 0 && <tr><td colSpan={6} className="text-center text-ink/50">Замовлень не знайдено</td></tr>}
        </tbody>
      </Table>
      <Pagination page={page} pages={Math.max(1, Math.ceil(total / PER_PAGE))} hrefFor={(p) => params({ page: p > 1 ? String(p) : undefined })} />
    </>
  );
}

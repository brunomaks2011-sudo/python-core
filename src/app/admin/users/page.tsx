import type { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guards";
import { formatDate } from "@/lib/utils";
import { PageTitle, Table } from "@/components/admin/ui";
import { Pagination } from "@/components/catalog/Pagination";

export const metadata = { title: "Користувачі" };
const PER_PAGE = 30;

export default async function AdminUsersPage({ searchParams }: { searchParams: Promise<{ q?: string; page?: string }> }) {
  await requireAdmin();
  const sp = await searchParams;
  const q = (sp.q ?? "").trim().slice(0, 100);
  const page = Math.max(1, Number(sp.page) || 1);
  const where: Prisma.UserWhereInput = q
    ? { OR: [{ email: { contains: q, mode: "insensitive" } }, { name: { contains: q, mode: "insensitive" } }, { phone: { contains: q } }] }
    : {};
  const [total, users] = await Promise.all([
    prisma.user.count({ where }),
    prisma.user.findMany({
      where,
      orderBy: { createdAt: "desc" },
      skip: (page - 1) * PER_PAGE,
      take: PER_PAGE,
      select: { id: true, name: true, email: true, phone: true, role: true, createdAt: true, _count: { select: { orders: true } } },
    }),
  ]);
  return (
    <>
      <PageTitle>Користувачі ({total})</PageTitle>
      <form className="mb-4 flex max-w-md gap-2">
        <input name="q" defaultValue={q} placeholder="Email, ім'я або телефон" className="input" />
        <button className="btn-secondary">Знайти</button>
      </form>
      <Table>
        <thead><tr><th>Ім&apos;я</th><th>Email</th><th>Телефон</th><th>Роль</th><th>Замовлень</th><th>Реєстрація</th></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td className="font-bold">{u.name}</td>
              <td>{u.email}</td>
              <td>{u.phone ?? "—"}</td>
              <td>{u.role === "ADMIN" ? <span className="rounded-full bg-sky-brand/10 px-2 py-0.5 text-xs font-bold text-sky-brand">ADMIN</span> : "Покупець"}</td>
              <td>{u._count.orders}</td>
              <td className="whitespace-nowrap">{formatDate(u.createdAt)}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Pagination page={page} pages={Math.max(1, Math.ceil(total / PER_PAGE))} hrefFor={(p) => `/admin/users?${new URLSearchParams({ ...(q ? { q } : {}), page: String(p) })}`} />
    </>
  );
}

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import type { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guards";
import { PageTitle, Table } from "@/components/admin/ui";
import { Pagination } from "@/components/catalog/Pagination";
import { ConfirmButton } from "@/components/admin/ConfirmButton";
import { deleteProductAction, quickUpdateProductAction } from "@/app/admin/actions";

export const metadata = { title: "Товари" };
const PER_PAGE = 20;

type Props = { searchParams: Promise<{ q?: string; page?: string; saved?: string }> };

export default async function AdminProductsPage({ searchParams }: Props) {
  await requireAdmin();
  const sp = await searchParams;
  const q = (sp.q ?? "").trim().slice(0, 100);
  const page = Math.max(1, Number(sp.page) || 1);
  const where: Prisma.ProductWhereInput = q
    ? { OR: [{ name: { contains: q, mode: "insensitive" } }, { sku: { contains: q, mode: "insensitive" } }] }
    : {};
  const [total, products] = await Promise.all([
    prisma.product.count({ where }),
    prisma.product.findMany({
      where,
      orderBy: { createdAt: "desc" },
      skip: (page - 1) * PER_PAGE,
      take: PER_PAGE,
      include: { category: { select: { name: true } } },
    }),
  ]);
  const href = (p: number) => `/admin/products?${new URLSearchParams({ ...(q ? { q } : {}), ...(p > 1 ? { page: String(p) } : {}) })}`;

  return (
    <>
      <PageTitle actions={<Link href="/admin/products/new" className="btn-primary">+ Додати товар</Link>}>Товари ({total})</PageTitle>
      {sp.saved && <p className="mb-4 rounded-xl bg-emerald-100 p-3 text-sm font-bold text-emerald-800">Товар збережено</p>}
      <form className="mb-4 flex max-w-md gap-2">
        <input name="q" defaultValue={q} placeholder="Пошук за назвою або артикулом" className="input" />
        <button className="btn-secondary">Знайти</button>
      </form>
      <Table>
        <thead>
          <tr><th></th><th>Товар</th><th>Категорія</th><th>Ціна, ₴ / Залишок</th><th>Статус</th><th></th></tr>
        </thead>
        <tbody>
          {products.map((p) => (
            <tr key={p.id}>
              <td className="w-14"><img src={p.images[0] || "/images/placeholder.svg"} alt="" className="h-12 w-12 max-w-none rounded-lg object-cover" /></td>
              <td>
                <Link href={`/admin/products/${p.id}`} className="font-bold hover:text-sky-brand">{p.name}</Link>
                <p className="text-xs text-ink/50">Арт. {p.sku}</p>
              </td>
              <td>{p.category.name}</td>
              <td>
                <form action={quickUpdateProductAction} className="flex items-center gap-1">
                  <input type="hidden" name="id" value={p.id} />
                  <input name="price" type="number" step="0.01" min="0.01" defaultValue={p.price / 100} className="input w-24 px-2 py-1" aria-label="Ціна" />
                  <input name="stock" type="number" min="0" defaultValue={p.stock} className={`input w-20 px-2 py-1 ${p.stock <= 5 ? "border-tomato-500/50" : ""}`} aria-label="Залишок" />
                  <button className="rounded-lg bg-ink px-2 py-1 text-xs font-bold text-white" title="Зберегти ціну і залишок">✓</button>
                </form>
              </td>
              <td>{p.isActive ? <span className="text-emerald-700">Активний</span> : <span className="text-ink/40">Прихований</span>}{p.isFeatured && " ⭐"}</td>
              <td className="whitespace-nowrap text-right">
                <Link href={`/admin/products/${p.id}`} className="mr-3 font-bold text-sky-brand">Змінити</Link>
                <form action={deleteProductAction} className="inline">
                  <input type="hidden" name="id" value={p.id} />
                  <ConfirmButton message={`Видалити «${p.name}»? Історія замовлень збережеться.`} className="font-bold text-tomato-600">Видалити</ConfirmButton>
                </form>
              </td>
            </tr>
          ))}
          {products.length === 0 && <tr><td colSpan={6} className="text-center text-ink/50">Нічого не знайдено</td></tr>}
        </tbody>
      </Table>
      <Pagination page={page} pages={Math.max(1, Math.ceil(total / PER_PAGE))} hrefFor={href} />
    </>
  );
}

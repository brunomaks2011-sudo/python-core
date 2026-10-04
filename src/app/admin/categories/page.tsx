/* eslint-disable @next/next/no-img-element */
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guards";
import { PageTitle, Panel } from "@/components/admin/ui";
import { CategoryForm, DeleteCategoryForm } from "@/components/admin/CategoryForms";

export const metadata = { title: "Категорії" };

export default async function AdminCategoriesPage() {
  await requireAdmin();
  const categories = await prisma.category.findMany({ orderBy: { sortOrder: "asc" }, include: { _count: { select: { products: true } } } });
  return (
    <>
      <PageTitle>Категорії (серії)</PageTitle>
      <Panel title="Нова категорія" className="mb-6">
        <CategoryForm />
      </Panel>
      <div className="space-y-4">
        {categories.map((c) => (
          <Panel key={c.id}>
            <div className="mb-3 flex items-center gap-3">
              <img src={c.image || "/images/placeholder.svg"} alt="" className="h-12 w-12 max-w-none rounded-lg object-cover" />
              <div className="flex-1">
                <p className="font-black">{c.name}</p>
                <p className="text-xs text-ink/50">/catalog/{c.slug} · {c._count.products} товарів</p>
              </div>
              <DeleteCategoryForm id={c.id} name={c.name} />
            </div>
            <CategoryForm category={c} />
          </Panel>
        ))}
      </div>
    </>
  );
}

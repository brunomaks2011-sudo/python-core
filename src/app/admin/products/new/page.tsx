import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guards";
import { PageTitle } from "@/components/admin/ui";
import { ProductForm } from "@/components/admin/ProductForm";

export const metadata = { title: "Новий товар" };

export default async function NewProductPage() {
  await requireAdmin();
  const categories = await prisma.category.findMany({ orderBy: { sortOrder: "asc" }, select: { id: true, name: true } });
  return (
    <>
      <PageTitle>Новий товар</PageTitle>
      {categories.length ? <ProductForm categories={categories} /> : <p>Спершу створіть хоча б одну категорію.</p>}
    </>
  );
}

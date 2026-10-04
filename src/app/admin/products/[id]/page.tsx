import Link from "next/link";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guards";
import { PageTitle } from "@/components/admin/ui";
import { ProductForm } from "@/components/admin/ProductForm";

export const metadata = { title: "Редагування товару" };

export default async function EditProductPage({ params }: { params: Promise<{ id: string }> }) {
  await requireAdmin();
  const { id } = await params;
  const [product, categories] = await Promise.all([
    prisma.product.findUnique({ where: { id } }),
    prisma.category.findMany({ orderBy: { sortOrder: "asc" }, select: { id: true, name: true } }),
  ]);
  if (!product) notFound();
  return (
    <>
      <PageTitle actions={<Link href={`/product/${product.slug}`} className="btn-ghost" target="_blank">Переглянути на сайті ↗</Link>}>
        {product.name}
      </PageTitle>
      <ProductForm product={product} categories={categories} />
    </>
  );
}

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";
import { CatalogView } from "@/components/catalog/CatalogView";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { parseCatalogQuery } from "@/lib/catalog";
import { prisma } from "@/lib/prisma";

type Props = {
  params: Promise<{ category: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const getCategory = cache((slug: string) => prisma.category.findUnique({ where: { slug } }));

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const { category: slug } = await params;
  const category = await getCategory(slug);
  if (!category) return {};
  const sp = await searchParams;
  return {
    title: `Конструктори LEGO® ${category.name}`,
    description: category.description ?? `Набори серії ${category.name} з доставкою по Україні.`,
    alternates: { canonical: `/catalog/${category.slug}` },
    openGraph: { images: category.image ? [category.image] : undefined },
    robots: Object.keys(sp).some((k) => k !== "page") ? { index: false, follow: true } : undefined,
  };
}

export default async function CategoryPage({ params, searchParams }: Props) {
  const { category: slug } = await params;
  const category = await getCategory(slug);
  if (!category) notFound();
  const query = parseCatalogQuery(await searchParams);
  return (
    <CatalogView
      query={query}
      basePath={`/catalog/${category.slug}`}
      lockedCategory={category.slug}
      title={category.name}
      description={category.description}
      breadcrumbs={<Breadcrumbs items={[{ name: "Каталог", href: "/catalog" }, { name: category.name }]} />}
    />
  );
}

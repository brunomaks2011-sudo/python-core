import type { Metadata } from "next";
import { CatalogView } from "@/components/catalog/CatalogView";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { parseCatalogQuery } from "@/lib/catalog";

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const sp = await searchParams;
  const filtered = Object.keys(sp).some((k) => k !== "page");
  return {
    title: "Каталог конструкторів",
    description: "Усі конструктори LEGO® у магазині «Цеглинка»: фільтри за серією, віком, ціною та кількістю деталей.",
    alternates: { canonical: "/catalog" },
    // Сторінки з фільтрами не індексуємо, щоб уникнути дублів
    robots: filtered ? { index: false, follow: true } : undefined,
  };
}

export default async function CatalogPage({ searchParams }: Props) {
  const query = parseCatalogQuery(await searchParams);
  return (
    <CatalogView
      query={query}
      basePath="/catalog"
      title="Каталог"
      breadcrumbs={<Breadcrumbs items={[{ name: "Каталог" }]} />}
    />
  );
}

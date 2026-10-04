import type { MetadataRoute } from "next";
import { prisma } from "@/lib/prisma";
import { absoluteUrl } from "@/config/site";

// Генерується на запит, щоб завжди містити актуальні товари
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [products, categories] = await Promise.all([
    prisma.product.findMany({ where: { isActive: true }, select: { slug: true, updatedAt: true, images: true } }),
    prisma.category.findMany({ select: { slug: true, updatedAt: true } }),
  ]);
  return [
    { url: absoluteUrl("/"), changeFrequency: "daily", priority: 1 },
    { url: absoluteUrl("/catalog"), changeFrequency: "daily", priority: 0.9 },
    ...categories.map((c) => ({
      url: absoluteUrl(`/catalog/${c.slug}`),
      lastModified: c.updatedAt,
      changeFrequency: "weekly" as const,
      priority: 0.8,
    })),
    ...products.map((p) => ({
      url: absoluteUrl(`/product/${p.slug}`),
      lastModified: p.updatedAt,
      changeFrequency: "weekly" as const,
      priority: 0.7,
      images: p.images.slice(0, 1).map((i) => (i.startsWith("http") ? i : absoluteUrl(i))),
    })),
  ];
}

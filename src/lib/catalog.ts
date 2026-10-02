import { z } from "zod";
import type { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { uahToKopecks } from "@/lib/money";

export const PAGE_SIZE = 12;

export const SORT_OPTIONS = {
  popular: "За популярністю",
  new: "Новинки",
  price_asc: "Від дешевих",
  price_desc: "Від дорогих",
} as const;
export type SortKey = keyof typeof SORT_OPTIONS;

export const AGE_OPTIONS = {
  "0-3": { label: "1–3 роки", min: 0, max: 3 },
  "4-6": { label: "4–6 років", min: 4, max: 6 },
  "7-9": { label: "7–9 років", min: 7, max: 9 },
  "10+": { label: "10+ років", min: 10, max: 99 },
} as const;
export type AgeKey = keyof typeof AGE_OPTIONS;

export const PIECES_OPTIONS = {
  "0-99": { label: "до 100", min: 0, max: 99 },
  "100-499": { label: "100–499", min: 100, max: 499 },
  "500-999": { label: "500–999", min: 500, max: 999 },
  "1000+": { label: "1000+", min: 1000, max: 1_000_000 },
} as const;
export type PiecesKey = keyof typeof PIECES_OPTIONS;

const toArray = (v: unknown) => (v === undefined ? [] : Array.isArray(v) ? v : [v]);
const optionalNumber = z.preprocess(
  (v) => (v === "" || v === undefined || Array.isArray(v) ? undefined : Number(v)),
  z.number().finite().min(0).max(1_000_000).optional(),
);

/** Валідація параметрів каталогу з URL. Невідомі/некоректні значення ігноруються. */
export const catalogQuerySchema = z.object({
  q: z.preprocess((v) => (typeof v === "string" ? v.trim().slice(0, 100) : undefined), z.string().optional()),
  category: z.preprocess(toArray, z.array(z.string().max(80))).catch([]),
  age: z.preprocess(toArray, z.array(z.enum(Object.keys(AGE_OPTIONS) as [AgeKey, ...AgeKey[]]))).catch([]),
  pieces: z.preprocess(toArray, z.array(z.enum(Object.keys(PIECES_OPTIONS) as [PiecesKey, ...PiecesKey[]]))).catch([]),
  priceMin: optionalNumber.catch(undefined),
  priceMax: optionalNumber.catch(undefined),
  inStock: z.preprocess((v) => v === "1" || v === "true", z.boolean()).catch(false),
  sort: z.enum(Object.keys(SORT_OPTIONS) as [SortKey, ...SortKey[]]).catch("popular"),
  page: z.coerce.number().int().min(1).max(10_000).catch(1),
});
export type CatalogQuery = z.infer<typeof catalogQuerySchema>;

export function parseCatalogQuery(params: Record<string, string | string[] | undefined>): CatalogQuery {
  return catalogQuerySchema.parse(params);
}

export function buildProductWhere(q: CatalogQuery): Prisma.ProductWhereInput {
  const and: Prisma.ProductWhereInput[] = [{ isActive: true }];
  if (q.q) {
    and.push({
      OR: [
        { name: { contains: q.q, mode: "insensitive" } },
        { sku: { contains: q.q, mode: "insensitive" } },
      ],
    });
  }
  if (q.category.length) and.push({ category: { slug: { in: q.category } } });
  if (q.age.length) and.push({ OR: q.age.map((k) => ({ ageMin: { gte: AGE_OPTIONS[k].min, lte: AGE_OPTIONS[k].max } })) });
  if (q.pieces.length)
    and.push({ OR: q.pieces.map((k) => ({ pieces: { gte: PIECES_OPTIONS[k].min, lte: PIECES_OPTIONS[k].max } })) });
  if (q.priceMin !== undefined) and.push({ price: { gte: uahToKopecks(q.priceMin) } });
  if (q.priceMax !== undefined) and.push({ price: { lte: uahToKopecks(q.priceMax) } });
  if (q.inStock) and.push({ stock: { gt: 0 } });
  return { AND: and };
}

export function buildOrderBy(sort: SortKey): Prisma.ProductOrderByWithRelationInput[] {
  switch (sort) {
    case "new":
      return [{ createdAt: "desc" }, { id: "asc" }];
    case "price_asc":
      return [{ price: "asc" }, { id: "asc" }];
    case "price_desc":
      return [{ price: "desc" }, { id: "asc" }];
    default:
      return [{ salesCount: "desc" }, { id: "asc" }];
  }
}

export const productCardSelect = {
  id: true,
  name: true,
  slug: true,
  sku: true,
  price: true,
  oldPrice: true,
  stock: true,
  pieces: true,
  ageMin: true,
  images: true,
  category: { select: { name: true, slug: true } },
} satisfies Prisma.ProductSelect;

export type ProductCardData = Prisma.ProductGetPayload<{ select: typeof productCardSelect }>;

export async function searchProducts(q: CatalogQuery) {
  const where = buildProductWhere(q);
  const [total, items] = await Promise.all([
    prisma.product.count({ where }),
    prisma.product.findMany({
      where,
      orderBy: buildOrderBy(q.sort),
      skip: (q.page - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
      select: productCardSelect,
    }),
  ]);
  return { total, items, pages: Math.max(1, Math.ceil(total / PAGE_SIZE)) };
}

export function getCategories() {
  return prisma.category.findMany({
    orderBy: [{ sortOrder: "asc" }, { name: "asc" }],
    include: { _count: { select: { products: { where: { isActive: true } } } } },
  });
}

export function getPopularProducts(take = 8) {
  return prisma.product.findMany({
    where: { isActive: true },
    orderBy: [{ isFeatured: "desc" }, { salesCount: "desc" }],
    take,
    select: productCardSelect,
  });
}

export function getNewProducts(take = 8) {
  return prisma.product.findMany({
    where: { isActive: true },
    orderBy: { createdAt: "desc" },
    take,
    select: productCardSelect,
  });
}

export function getProductBySlug(slug: string) {
  return prisma.product.findFirst({ where: { slug, isActive: true }, include: { category: true } });
}

export function getSimilarProducts(product: { id: string; categoryId: string; price: number }, take = 4) {
  return prisma.product.findMany({
    where: { isActive: true, categoryId: product.categoryId, id: { not: product.id } },
    orderBy: [{ salesCount: "desc" }],
    take,
    select: productCardSelect,
  });
}

/** Будує query string для посилань каталогу, зберігаючи поточні фільтри. */
export function catalogHref(base: string, q: Partial<CatalogQuery>, overrides: Record<string, string | number | undefined> = {}) {
  const params = new URLSearchParams();
  if (q.q) params.set("q", q.q);
  q.category?.forEach((c) => params.append("category", c));
  q.age?.forEach((a) => params.append("age", a));
  q.pieces?.forEach((p) => params.append("pieces", p));
  if (q.priceMin !== undefined) params.set("priceMin", String(q.priceMin));
  if (q.priceMax !== undefined) params.set("priceMax", String(q.priceMax));
  if (q.inStock) params.set("inStock", "1");
  if (q.sort && q.sort !== "popular") params.set("sort", q.sort);
  if (q.page && q.page > 1) params.set("page", String(q.page));
  for (const [k, v] of Object.entries(overrides)) {
    if (v === undefined || v === "") params.delete(k);
    else params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `${base}?${s}` : base;
}

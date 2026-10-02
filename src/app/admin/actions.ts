"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { Prisma } from "@prisma/client";
import { z } from "zod";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/auth-guards";
import { cuidSchema, fieldErrors } from "@/lib/validation";
import { uahToKopecks } from "@/lib/money";
import { slugify } from "@/lib/utils";
import { deleteImage, saveImage, UploadError } from "@/lib/storage";
import { decrementStock, InsufficientStockError, restoreStock } from "@/lib/orders/stock";
import type { FormState } from "@/app/actions/auth";

// УВАГА: кожна дія починається з requireAdmin() — Server Actions доступні як публічні POST-ендпоінти.

const uah = z.coerce.number().finite().min(0, "Не може бути від'ємним").max(10_000_000);
const optionalUah = z.preprocess((v) => (v === "" || v == null ? undefined : v), uah.optional());
const intField = (min: number, max: number) => z.coerce.number().int("Ціле число").min(min).max(max);
const checkbox = z.preprocess((v) => v === "on" || v === "true", z.boolean());

const productSchema = z
  .object({
    name: z.string().trim().min(2, "Вкажіть назву").max(200),
    slug: z.string().trim().max(100).optional(),
    sku: z.string().trim().min(1, "Вкажіть артикул").max(40).regex(/^[\w-]+$/, "Лише латиниця, цифри, - та _"),
    description: z.string().trim().min(1, "Додайте опис").max(10_000),
    categoryId: cuidSchema,
    price: uah.refine((v) => v > 0, "Ціна має бути більшою за 0"),
    oldPrice: optionalUah,
    stock: intField(0, 1_000_000),
    pieces: intField(1, 100_000),
    ageMin: intField(0, 99),
    weightGrams: intField(1, 100_000),
    isActive: checkbox,
    isFeatured: checkbox,
    images: z.array(z.string().max(500).regex(/^(\/(images|uploads)\/[\w./-]+|https:\/\/[\w.-]+\.public\.blob\.vercel-storage\.com\/[\w./-]+)$/)).max(12),
  })
  .refine((d) => d.oldPrice === undefined || d.oldPrice === 0 || d.oldPrice > d.price, {
    path: ["oldPrice"],
    message: "Стара ціна має бути більшою за поточну",
  });

export async function saveProductAction(_: FormState, formData: FormData): Promise<FormState> {
  await requireAdmin();
  const id = formData.get("id") ? cuidSchema.parse(formData.get("id")) : null;
  const parsed = productSchema.safeParse({
    ...Object.fromEntries([...formData.entries()].filter(([k]) => k !== "images" && k !== "newImages")),
    images: formData.getAll("images").map(String),
  });
  if (!parsed.success) return { error: "Перевірте поля форми", fieldErrors: fieldErrors(parsed.error) };
  const d = parsed.data;

  const files = formData.getAll("newImages").filter((f): f is File => f instanceof File && f.size > 0);
  if (d.images.length + files.length > 12) return { error: "Максимум 12 зображень" };
  const uploaded: string[] = [];
  try {
    for (const f of files) uploaded.push(await saveImage(f));
  } catch (e) {
    await Promise.all(uploaded.map(deleteImage));
    if (e instanceof UploadError) return { error: e.message };
    throw e;
  }

  const data = {
    name: d.name,
    slug: slugify(d.slug || `${d.name}-${d.sku}`),
    sku: d.sku,
    description: d.description,
    categoryId: d.categoryId,
    price: uahToKopecks(d.price),
    oldPrice: d.oldPrice ? uahToKopecks(d.oldPrice) : null,
    stock: d.stock,
    pieces: d.pieces,
    ageMin: d.ageMin,
    weightGrams: d.weightGrams,
    isActive: d.isActive,
    isFeatured: d.isFeatured,
    images: [...d.images, ...uploaded],
  };

  try {
    if (id) {
      const before = await prisma.product.findUnique({ where: { id }, select: { images: true } });
      await prisma.product.update({ where: { id }, data });
      const removed = (before?.images ?? []).filter((u) => !data.images.includes(u));
      await Promise.all(removed.map(deleteImage));
    } else {
      await prisma.product.create({ data });
    }
  } catch (e) {
    await Promise.all(uploaded.map(deleteImage));
    if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === "P2002") {
      const target = String(e.meta?.target ?? "");
      return { fieldErrors: target.includes("sku") ? { sku: "Такий артикул уже існує" } : { slug: "Такий slug уже існує" } };
    }
    throw e;
  }
  revalidatePath("/", "layout");
  redirect("/admin/products?saved=1");
}

export async function quickUpdateProductAction(formData: FormData) {
  await requireAdmin();
  const parsed = z
    .object({ id: cuidSchema, price: uah.refine((v) => v > 0), stock: intField(0, 1_000_000) })
    .safeParse(Object.fromEntries(formData));
  if (!parsed.success) return;
  await prisma.product.update({
    where: { id: parsed.data.id },
    data: { price: uahToKopecks(parsed.data.price), stock: parsed.data.stock },
  });
  revalidatePath("/", "layout");
}

export async function deleteProductAction(formData: FormData) {
  await requireAdmin();
  const id = cuidSchema.parse(formData.get("id"));
  const product = await prisma.product.delete({ where: { id } }).catch(() => null);
  if (product) await Promise.all(product.images.map(deleteImage));
  revalidatePath("/", "layout");
}

const categorySchema = z.object({
  name: z.string().trim().min(2, "Вкажіть назву").max(100),
  slug: z.string().trim().max(100).optional(),
  description: z.string().trim().max(1000).optional(),
  sortOrder: z.coerce.number().int().min(0).max(10_000).catch(0),
});

export async function saveCategoryAction(_: FormState, formData: FormData): Promise<FormState> {
  await requireAdmin();
  const id = formData.get("id") ? cuidSchema.parse(formData.get("id")) : null;
  const parsed = categorySchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };
  const file = formData.get("image");
  let image: string | undefined;
  try {
    if (file instanceof File && file.size > 0) image = await saveImage(file);
  } catch (e) {
    if (e instanceof UploadError) return { error: e.message };
    throw e;
  }
  const data = {
    name: parsed.data.name,
    slug: slugify(parsed.data.slug || parsed.data.name),
    description: parsed.data.description || null,
    sortOrder: parsed.data.sortOrder,
    ...(image ? { image } : {}),
  };
  if (!data.slug) return { fieldErrors: { slug: "Вкажіть slug латиницею" } };
  try {
    if (id) await prisma.category.update({ where: { id }, data });
    else await prisma.category.create({ data: { ...data, image: image ?? "/images/placeholder.svg" } });
  } catch (e) {
    if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === "P2002") return { fieldErrors: { slug: "Такий slug уже існує" } };
    throw e;
  }
  revalidatePath("/", "layout");
  return { success: id ? "Категорію оновлено" : "Категорію додано" };
}

export async function deleteCategoryAction(_: FormState, formData: FormData): Promise<FormState> {
  await requireAdmin();
  const id = cuidSchema.parse(formData.get("id"));
  const count = await prisma.product.count({ where: { categoryId: id } });
  if (count > 0) return { error: `Неможливо видалити: у категорії ${count} товар(ів). Спершу перенесіть або видаліть їх.` };
  await prisma.category.delete({ where: { id } });
  revalidatePath("/", "layout");
  return { success: "Категорію видалено" };
}

const orderUpdateSchema = z.object({
  id: cuidSchema,
  status: z.enum(["NEW", "PAID", "SHIPPED", "DELIVERED", "CANCELLED"]),
  trackingNumber: z
    .string()
    .trim()
    .max(40)
    .regex(/^[\w-]*$/, "ТТН — лише цифри та латиниця")
    .optional(),
});

export async function updateOrderAction(_: FormState, formData: FormData): Promise<FormState> {
  await requireAdmin();
  const parsed = orderUpdateSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };
  const { id, status, trackingNumber } = parsed.data;

  try {
    await prisma.$transaction(async (tx) => {
      const order = await tx.order.findUniqueOrThrow({ where: { id }, include: { items: true } });
      // Скасування повертає товари на склад; відновлення скасованого — списує знову
      if (status === "CANCELLED" && order.status !== "CANCELLED") {
        await restoreStock(tx, order.items);
      } else if (order.status === "CANCELLED" && status !== "CANCELLED") {
        await decrementStock(
          tx,
          order.items.filter((i) => i.productId).map((i) => ({ productId: i.productId!, quantity: i.quantity, name: i.productName })),
        );
      }
      const markPaid =
        order.paymentStatus !== "PAID" && (status === "PAID" || (status === "DELIVERED" && order.paymentMethod === "COD"));
      await tx.order.update({
        where: { id },
        data: {
          status,
          trackingNumber: trackingNumber || null,
          ...(markPaid ? { paymentStatus: "PAID", paidAt: new Date() } : {}),
        },
      });
    });
  } catch (e) {
    if (e instanceof InsufficientStockError) return { error: `Не вдалося відновити замовлення: ${e.message}` };
    throw e;
  }
  revalidatePath("/admin/orders");
  revalidatePath(`/admin/orders/${id}`);
  return { success: "Замовлення оновлено" };
}

const settingsSchema = z.object({
  freeShippingThreshold: uah,
  ukrposhtaRate: uah,
  npWarehouseFallbackRate: uah,
  npCourierFallbackRate: uah,
});

export async function saveSettingsAction(_: FormState, formData: FormData): Promise<FormState> {
  await requireAdmin();
  const parsed = settingsSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };
  const data = Object.fromEntries(Object.entries(parsed.data).map(([k, v]) => [k, uahToKopecks(v)])) as Record<
    keyof typeof parsed.data,
    number
  >;
  await prisma.storeSettings.upsert({ where: { id: 1 }, update: data, create: { id: 1, ...data } });
  revalidatePath("/", "layout");
  return { success: "Налаштування збережено" };
}

"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { prisma } from "@/lib/prisma";
import { getOrCreateCartId } from "@/lib/cart/server";
import { clampQuantity } from "@/lib/cart/calc";
import { cuidSchema, quantitySchema } from "@/lib/validation";

export type CartActionResult = { ok: true; quantity: number; message?: string } | { ok: false; error: string };

const addSchema = z.object({ productId: cuidSchema, quantity: quantitySchema.refine((q) => q >= 1) });
const setSchema = z.object({ productId: cuidSchema, quantity: quantitySchema });

function revalidateCart() {
  revalidatePath("/", "layout");
}

export async function addToCart(productId: string, quantity = 1): Promise<CartActionResult> {
  const parsed = addSchema.safeParse({ productId, quantity });
  if (!parsed.success) return { ok: false, error: "Некоректні дані" };

  const product = await prisma.product.findFirst({
    where: { id: parsed.data.productId, isActive: true },
    select: { id: true, stock: true },
  });
  if (!product) return { ok: false, error: "Товар не знайдено" };
  if (product.stock <= 0) return { ok: false, error: "Товару немає в наявності" };

  const cartId = await getOrCreateCartId();
  const existing = await prisma.cartItem.findUnique({
    where: { cartId_productId: { cartId, productId: product.id } },
  });
  const wanted = (existing?.quantity ?? 0) + parsed.data.quantity;
  const qty = clampQuantity(wanted, product.stock);

  await prisma.cartItem.upsert({
    where: { cartId_productId: { cartId, productId: product.id } },
    update: { quantity: qty },
    create: { cartId, productId: product.id, quantity: qty },
  });
  revalidateCart();
  return {
    ok: true,
    quantity: qty,
    message: qty < wanted ? `Доступно лише ${product.stock} шт.` : "Додано в кошик",
  };
}

export async function setCartItemQuantity(productId: string, quantity: number): Promise<CartActionResult> {
  const parsed = setSchema.safeParse({ productId, quantity });
  if (!parsed.success) return { ok: false, error: "Некоректна кількість" };

  const cartId = await getOrCreateCartId();
  if (parsed.data.quantity === 0) {
    await prisma.cartItem.deleteMany({ where: { cartId, productId: parsed.data.productId } });
    revalidateCart();
    return { ok: true, quantity: 0 };
  }
  const product = await prisma.product.findUnique({
    where: { id: parsed.data.productId },
    select: { stock: true, isActive: true },
  });
  if (!product || !product.isActive) return { ok: false, error: "Товар недоступний" };
  const qty = clampQuantity(parsed.data.quantity, product.stock);
  if (qty === 0) return { ok: false, error: "Товару немає в наявності" };

  await prisma.cartItem.updateMany({ where: { cartId, productId: parsed.data.productId }, data: { quantity: qty } });
  revalidateCart();
  return { ok: true, quantity: qty, message: qty < parsed.data.quantity ? `Доступно лише ${product.stock} шт.` : undefined };
}

export async function removeCartItem(productId: string): Promise<CartActionResult> {
  return setCartItemQuantity(productId, 0);
}

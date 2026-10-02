import "server-only";
import { cookies } from "next/headers";
import { randomBytes } from "node:crypto";
import { prisma } from "@/lib/prisma";
import { auth } from "@/auth";
import { computeCartTotals, mergeCartLines } from "@/lib/cart/calc";

export const GUEST_CART_COOKIE = "cart_token";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 60; // 60 днів

const cartInclude = {
  items: {
    orderBy: { id: "asc" as const },
    include: {
      product: {
        select: {
          id: true, name: true, slug: true, sku: true, price: true, oldPrice: true,
          stock: true, images: true, isActive: true, weightGrams: true,
        },
      },
    },
  },
};

async function findCart() {
  const session = await auth();
  if (session?.user?.id) {
    return prisma.cart.findUnique({ where: { userId: session.user.id }, include: cartInclude });
  }
  const token = (await cookies()).get(GUEST_CART_COOKIE)?.value;
  if (!token) return null;
  return prisma.cart.findUnique({ where: { guestToken: token }, include: cartInclude });
}

export type CartView = Awaited<ReturnType<typeof getCart>>;

/** Кошик поточного відвідувача для відображення (тільки читання). */
export async function getCart() {
  const cart = await findCart();
  const items = cart?.items ?? [];
  const totals = computeCartTotals(
    items.map((i) => ({
      productId: i.productId,
      quantity: i.quantity,
      unitPrice: i.product.price,
      stock: i.product.stock,
      isActive: i.product.isActive,
    })),
  );
  const weightGrams = items.reduce((s, i) => s + i.product.weightGrams * i.quantity, 0);
  return { id: cart?.id ?? null, items, ...totals, weightGrams };
}

export async function getCartCount(): Promise<number> {
  const cart = await findCart();
  return cart?.items.reduce((s, i) => s + i.quantity, 0) ?? 0;
}

/** Знаходить або створює кошик. Викликати лише з Server Actions / Route Handlers (може ставити cookie). */
export async function getOrCreateCartId(): Promise<string> {
  const session = await auth();
  if (session?.user?.id) {
    const cart = await prisma.cart.upsert({
      where: { userId: session.user.id },
      update: {},
      create: { userId: session.user.id },
      select: { id: true },
    });
    return cart.id;
  }
  const store = await cookies();
  const token = store.get(GUEST_CART_COOKIE)?.value;
  if (token) {
    const cart = await prisma.cart.findUnique({ where: { guestToken: token }, select: { id: true } });
    if (cart) return cart.id;
  }
  const newToken = randomBytes(24).toString("base64url");
  const cart = await prisma.cart.create({ data: { guestToken: newToken }, select: { id: true } });
  store.set(GUEST_CART_COOKIE, newToken, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: COOKIE_MAX_AGE,
  });
  return cart.id;
}

/**
 * Переносить гостьовий кошик (з cookie) у кошик користувача після входу/реєстрації.
 * Викликати з Server Action після успішної автентифікації.
 */
export async function mergeGuestCartIntoUser(userId: string): Promise<void> {
  const store = await cookies();
  const token = store.get(GUEST_CART_COOKIE)?.value;
  if (!token) return;
  const guest = await prisma.cart.findUnique({
    where: { guestToken: token },
    include: { items: { include: { product: { select: { stock: true } } } } },
  });
  store.delete(GUEST_CART_COOKIE);
  if (!guest || guest.items.length === 0) {
    if (guest) await prisma.cart.delete({ where: { id: guest.id } }).catch(() => {});
    return;
  }

  await prisma.$transaction(async (tx) => {
    const userCart = await tx.cart.upsert({
      where: { userId },
      update: {},
      create: { userId },
      include: { items: { include: { product: { select: { stock: true } } } } },
    });
    const stock = new Map<string, number>();
    for (const i of [...userCart.items, ...guest.items]) stock.set(i.productId, i.product.stock);
    const merged = mergeCartLines(userCart.items, guest.items, (id) => stock.get(id) ?? 0);

    await tx.cartItem.deleteMany({ where: { cartId: userCart.id } });
    if (merged.length) {
      await tx.cartItem.createMany({ data: merged.map((m) => ({ cartId: userCart.id, ...m })) });
    }
    await tx.cart.delete({ where: { id: guest.id } });
  });
}

export async function clearCart(cartId: string) {
  await prisma.cartItem.deleteMany({ where: { cartId } });
}

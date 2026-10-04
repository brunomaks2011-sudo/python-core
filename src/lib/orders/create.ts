import "server-only";
import { randomBytes, randomInt } from "node:crypto";
import { Prisma, type DeliveryMethod } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { computeCartTotals, computeOrderTotal } from "@/lib/cart/calc";
import { getDeliveryQuote } from "@/lib/delivery";
import { pickupAddress } from "@/lib/settings";
import { decrementStock } from "./stock";
import type { CheckoutInput, DeliveryInput } from "./schema";

export class CheckoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CheckoutError";
  }
}

/** Номер замовлення: РРММДД-XXXXX, напр. 261002-48213 */
export function generateOrderNumber(now = new Date()): string {
  const d = now.toISOString().slice(2, 10).replace(/-/g, "");
  return `${d}-${randomInt(10000, 99999)}`;
}

function deliveryData(d: DeliveryInput): Prisma.InputJsonObject {
  const { method: _method, ...rest } = d;
  if (d.method === "PICKUP") return { address: pickupAddress() };
  return rest as Prisma.InputJsonObject;
}

/**
 * Створює замовлення з поточного кошика:
 * - ціни беруться з БД (клієнту не довіряємо);
 * - вартість доставки перераховується на сервері;
 * - залишки списуються в тій самій транзакції, що й створення замовлення.
 */
export async function createOrderFromCart(input: CheckoutInput, ctx: { cartId: string; userId: string | null }) {
  const cart = await prisma.cart.findUnique({
    where: { id: ctx.cartId },
    include: { items: { include: { product: true } } },
  });
  if (!cart || cart.items.length === 0) throw new CheckoutError("Кошик порожній");

  for (const i of cart.items) {
    if (!i.product.isActive) throw new CheckoutError(`Товар «${i.product.name}» більше недоступний. Видаліть його з кошика.`);
  }
  const totals = computeCartTotals(
    cart.items.map((i) => ({
      productId: i.productId,
      quantity: i.quantity,
      unitPrice: i.product.price,
      stock: i.product.stock,
      isActive: i.product.isActive,
    })),
  );
  if (totals.hasUnavailable) {
    throw new CheckoutError("Деяких товарів немає в потрібній кількості. Оновіть кошик і спробуйте ще раз.");
  }

  const weightGrams = cart.items.reduce((s, i) => s + i.product.weightGrams * i.quantity, 0);
  const cityRef = "cityRef" in input.delivery ? input.delivery.cityRef : undefined;
  const quote = await getDeliveryQuote({
    method: input.delivery.method as DeliveryMethod,
    cityRef,
    itemsTotal: totals.itemsTotal,
    weightGrams,
  });

  const lines = cart.items.map((i) => ({ productId: i.productId, quantity: i.quantity, name: i.product.name }));

  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      return await prisma.$transaction(
        async (tx) => {
          await decrementStock(tx, lines);
          const order = await tx.order.create({
            data: {
              number: generateOrderNumber(),
              accessToken: randomBytes(24).toString("base64url"),
              userId: ctx.userId,
              contactName: input.contact.name,
              contactPhone: input.contact.phone,
              contactEmail: input.contact.email,
              comment: input.comment || null,
              paymentMethod: input.paymentMethod,
              paymentProvider: input.paymentMethod === "LIQPAY" ? "liqpay" : null,
              deliveryMethod: input.delivery.method,
              deliveryData: deliveryData(input.delivery),
              deliveryCost: quote.cost,
              itemsTotal: totals.itemsTotal,
              total: computeOrderTotal(totals.itemsTotal, quote.cost),
              items: {
                create: cart.items.map((i) => ({
                  productId: i.productId,
                  productName: i.product.name,
                  productSku: i.product.sku,
                  quantity: i.quantity,
                  unitPrice: i.product.price,
                })),
              },
            },
            include: { items: true },
          });
          await tx.cartItem.deleteMany({ where: { cartId: cart.id } });
          return order;
        },
        { timeout: 15_000 },
      );
    } catch (e) {
      // Колізія номера замовлення — пробуємо з іншим номером
      if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === "P2002") continue;
      throw e;
    }
  }
  throw new CheckoutError("Не вдалося створити замовлення, спробуйте ще раз");
}

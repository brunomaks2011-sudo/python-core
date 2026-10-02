"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";
import { getOrCreateCartId } from "@/lib/cart/server";
import { checkoutSchema } from "@/lib/orders/schema";
import { CheckoutError, createOrderFromCart } from "@/lib/orders/create";
import { InsufficientStockError } from "@/lib/orders/stock";
import { startOnlinePayment } from "@/lib/orders/payment";
import { getOnlinePaymentProvider } from "@/lib/payments";
import { clientIp, rateLimit } from "@/lib/rate-limit";
import { fieldErrors } from "@/lib/validation";
import { sendOrderConfirmation } from "@/lib/orders/notify";

export type CheckoutResult =
  | { ok: true; redirectUrl: string }
  | { ok: false; error: string; fieldErrors?: Record<string, string> };

export async function submitCheckout(raw: unknown): Promise<CheckoutResult> {
  const ip = clientIp(await headers());
  const limit = await rateLimit(`checkout:${ip}`, 10, 10 * 60 * 1000);
  if (!limit.ok) return { ok: false, error: "Забагато спроб. Спробуйте за кілька хвилин." };

  const parsed = checkoutSchema.safeParse(raw);
  if (!parsed.success) {
    return { ok: false, error: "Перевірте правильність заповнення форми", fieldErrors: fieldErrors(parsed.error) };
  }
  const input = parsed.data;
  if (input.paymentMethod === "LIQPAY" && !getOnlinePaymentProvider()) {
    return { ok: false, error: "Онлайн-оплата тимчасово недоступна. Оберіть оплату при отриманні." };
  }

  const session = await auth();
  const userId = session?.user?.id ?? null;
  const cartId = await getOrCreateCartId();

  let order;
  try {
    order = await createOrderFromCart(input, { cartId, userId });
  } catch (e) {
    if (e instanceof CheckoutError || e instanceof InsufficientStockError) return { ok: false, error: e.message };
    console.error("[checkout] failed:", e);
    return { ok: false, error: "Не вдалося оформити замовлення. Спробуйте ще раз." };
  }

  if (userId && input.saveAddress && input.delivery.method !== "PICKUP") {
    const d = input.delivery;
    const existing = await prisma.address.count({ where: { userId } });
    await prisma.address.create({
      data: {
        userId,
        recipientName: input.contact.name,
        recipientPhone: input.contact.phone,
        deliveryMethod: d.method,
        city: d.city,
        cityRef: "cityRef" in d ? d.cityRef : undefined,
        warehouse: "warehouse" in d ? d.warehouse : undefined,
        warehouseRef: "warehouseRef" in d ? d.warehouseRef : undefined,
        street: "street" in d ? d.street : undefined,
        building: "building" in d ? d.building : undefined,
        apartment: "apartment" in d ? d.apartment : undefined,
        postalCode: "postalCode" in d ? d.postalCode : undefined,
        isDefault: existing === 0,
      },
    }).catch((e) => console.error("[checkout] save address failed:", e));
  }

  await sendOrderConfirmation(order);
  revalidatePath("/", "layout");

  const orderUrl = `/order/${order.number}?t=${order.accessToken}`;
  if (input.paymentMethod === "LIQPAY") {
    try {
      const { url } = await startOnlinePayment(order);
      return { ok: true, redirectUrl: url };
    } catch (e) {
      console.error("[checkout] payment init failed:", e);
      return { ok: true, redirectUrl: `${orderUrl}&payment=error` };
    }
  }
  return { ok: true, redirectUrl: `${orderUrl}&new=1` };
}

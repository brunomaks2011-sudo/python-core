import { NextResponse } from "next/server";
import { z } from "zod";
import { getCart } from "@/lib/cart/server";
import { getDeliveryQuote } from "@/lib/delivery";
import { DELIVERY_METHOD_KEYS } from "@/lib/delivery/methods";
import { computeOrderTotal } from "@/lib/cart/calc";

const bodySchema = z.object({
  method: z.enum(DELIVERY_METHOD_KEYS as [string, ...string[]]),
  cityRef: z.string().regex(/^[0-9a-f-]{36}$/i).optional().nullable(),
});

/** Розрахунок вартості доставки для поточного кошика (в реальному часі на сторінці оформлення). */
export async function POST(req: Request) {
  const parsed = bodySchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "Некоректні дані" }, { status: 400 });
  const cart = await getCart();
  const quote = await getDeliveryQuote({
    method: parsed.data.method as never,
    cityRef: parsed.data.cityRef,
    itemsTotal: cart.itemsTotal,
    weightGrams: cart.weightGrams,
  });
  return NextResponse.json({ quote, itemsTotal: cart.itemsTotal, total: computeOrderTotal(cart.itemsTotal, quote.cost) });
}

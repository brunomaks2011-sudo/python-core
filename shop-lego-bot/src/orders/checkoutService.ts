import type { Checkout, CheckoutStep } from "../generated/prisma/client.js";
import type { Prisma, PrismaClient } from "../database/client.js";

export type CheckoutPatch = Partial<
  Pick<
    Prisma.CheckoutUncheckedUpdateInput,
    | "step"
    | "editingField"
    | "productId"
    | "quantity"
    | "fullName"
    | "phone"
    | "city"
    | "deliveryPoint"
    | "paymentMethod"
    | "quotedUnitPrice"
    | "profileOffered"
  >
>;

/** Наступний крок оформлення: запитуємо лише те, чого ще немає в чернетці. */
export function nextCheckoutStep(c: Checkout, opts: { hasSavedProfile: boolean }): CheckoutStep {
  if (c.productId === null) return "PRODUCT";
  if (c.quantity === null) return "QUANTITY";
  const nothingEntered = !c.fullName && !c.phone && !c.city && !c.deliveryPoint;
  if (!c.profileOffered && opts.hasSavedProfile && nothingEntered) return "REUSE_PROFILE";
  if (!c.fullName) return "FULL_NAME";
  if (!c.phone) return "PHONE";
  if (!c.city) return "CITY";
  if (!c.deliveryPoint) return "DELIVERY_POINT";
  if (!c.paymentMethod) return "PAYMENT";
  return "SUMMARY";
}

/** Чернетки оформлення замовлень (по одній на покупця) у базі даних. */
export class CheckoutService {
  constructor(private readonly prisma: PrismaClient) {}

  async get(customerId: number): Promise<Checkout | null> {
    return this.prisma.checkout.findUnique({ where: { customerId } });
  }

  async getActive(customerId: number): Promise<Checkout | null> {
    const c = await this.get(customerId);
    return c && c.status === "ACTIVE" ? c : null;
  }

  /** Починає нове оформлення. Старі кнопки попередньої чернетки перестають діяти (новий nonce). */
  async start(customerId: number, init: { productId?: number | null; quantity?: number | null } = {}): Promise<Checkout> {
    const reset = {
      status: "ACTIVE" as const,
      step: "PRODUCT" as const,
      editingField: null,
      productId: init.productId ?? null,
      quantity: init.quantity ?? null,
      fullName: null,
      phone: null,
      city: null,
      deliveryPoint: null,
      paymentMethod: null,
      quotedUnitPrice: null,
      profileOffered: false,
      orderId: null,
    };
    return this.prisma.checkout.upsert({
      where: { customerId },
      create: { customerId, ...reset },
      update: { ...reset, nonce: { increment: 1 } },
    });
  }

  /** Оновлює активну чернетку з указаним nonce; повертає null, якщо чернетка вже неактуальна. */
  async update(customerId: number, nonce: number, patch: CheckoutPatch): Promise<Checkout | null> {
    const res = await this.prisma.checkout.updateMany({
      where: { customerId, nonce, status: "ACTIVE" },
      data: patch,
    });
    if (res.count === 0) return null;
    return this.get(customerId);
  }

  async cancel(customerId: number, nonce?: number): Promise<boolean> {
    const res = await this.prisma.checkout.updateMany({
      where: { customerId, status: "ACTIVE", ...(nonce !== undefined ? { nonce } : {}) },
      data: { status: "CANCELED", editingField: null },
    });
    return res.count > 0;
  }

  /** Позначає покинуті чернетки простроченими (товар у чернетках не резервується). */
  async expireStale(ttlHours: number): Promise<number> {
    const res = await this.prisma.checkout.updateMany({
      where: { status: "ACTIVE", updatedAt: { lt: new Date(Date.now() - ttlHours * 3600_000) } },
      data: { status: "EXPIRED" },
    });
    return res.count;
  }
}

import type { Checkout, OrderStatus, StockState } from "../generated/prisma/client.js";
import { Prisma, inTransaction, type PrismaClient, type Tx } from "../database/client.js";
import { toView } from "../catalog/productService.js";
import type { InventoryService, StockLevels } from "../inventory/inventoryService.js";
import { InsufficientStockError, InvalidTransitionError, NotFoundError } from "../lib/errors.js";
import type { OrderNotifier, StockSnapshot } from "../notifications/orderNotifier.js";
import { ORDER_STATUS_LABELS, canTransition } from "./orderStatus.js";
import { ORDER_INCLUDE, type OrderActor, type OrderFull, type OrderWithHistory } from "./types.js";

export type PlaceOrderResult =
  | { kind: "created"; order: OrderFull }
  | { kind: "duplicate"; order: OrderFull }
  | { kind: "stale" }
  | { kind: "incomplete" }
  | { kind: "unavailable" }
  | { kind: "price_changed"; oldPrice: Prisma.Decimal | null; newPrice: Prisma.Decimal }
  | { kind: "insufficient_stock"; available: number };

export type OrderListFilter = "new" | "work" | "shipped" | "done" | "canceled" | "returns" | "all";

export const ORDER_FILTER_STATUSES: Record<OrderListFilter, OrderStatus[] | null> = {
  new: ["NEW", "AWAITING_CONFIRMATION"],
  work: ["CONFIRMED", "PAID", "PACKING"],
  shipped: ["SHIPPED"],
  done: ["DELIVERED"],
  canceled: ["CANCELED"],
  returns: ["RETURNED"],
  all: null,
};

const STATUS_TIMESTAMP: Partial<Record<OrderStatus, keyof Prisma.OrderUpdateInput>> = {
  CONFIRMED: "confirmedAt",
  PAID: "paidAt",
  SHIPPED: "shippedAt",
  DELIVERED: "deliveredAt",
  CANCELED: "canceledAt",
  RETURNED: "returnedAt",
};

export class OrderService {
  constructor(
    private readonly prisma: PrismaClient,
    private readonly inventory: InventoryService,
    private readonly notifier: OrderNotifier,
  ) {}

  /**
   * Оформлює замовлення з чернетки покупця в одній транзакції:
   * блокує чернетку (захист від подвійного натискання), повторно перевіряє ціну
   * й наявність, атомарно резервує товар, створює замовлення, історію статусів
   * і сповіщення власнику (outbox).
   */
  async placeOrder(params: { customerId: number; nonce: number }): Promise<PlaceOrderResult> {
    try {
      return await inTransaction(this.prisma, async (tx) => {
        const locked = await tx.$queryRaw<Array<{ id: number }>>`
          SELECT id FROM checkouts WHERE customer_id = ${params.customerId} FOR UPDATE`;
        if (locked.length === 0) return { kind: "stale" } as const;
        const checkout = await tx.checkout.findUniqueOrThrow({ where: { customerId: params.customerId } });

        if (checkout.nonce !== params.nonce || checkout.status !== "ACTIVE") {
          if (checkout.nonce === params.nonce && checkout.status === "SUBMITTED" && checkout.orderId) {
            const existing = await tx.order.findUnique({ where: { id: checkout.orderId }, include: ORDER_INCLUDE });
            if (existing) return { kind: "duplicate", order: existing } as const;
          }
          return { kind: "stale" } as const;
        }
        if (!isComplete(checkout)) return { kind: "incomplete" } as const;

        const productRows = await tx.$queryRaw<Array<{ id: number }>>`
          SELECT id FROM products WHERE id = ${checkout.productId} FOR UPDATE`;
        const product = productRows.length > 0 ? await tx.product.findUnique({ where: { id: checkout.productId } }) : null;
        if (!product || product.status !== "ACTIVE") return { kind: "unavailable" } as const;

        if (!checkout.quotedUnitPrice || !checkout.quotedUnitPrice.equals(product.price)) {
          return { kind: "price_changed", oldPrice: checkout.quotedUnitPrice, newPrice: product.price } as const;
        }
        const view = toView(product);
        if (view.available < checkout.quantity) {
          return { kind: "insufficient_stock", available: view.available } as const;
        }

        const lineTotal = product.price.mul(checkout.quantity);
        const created = await tx.order.create({
          data: {
            customerId: checkout.customerId,
            status: "NEW",
            stockState: "RESERVED",
            totalAmount: lineTotal,
            fullName: checkout.fullName,
            phone: checkout.phone,
            city: checkout.city,
            deliveryPoint: checkout.deliveryPoint,
            paymentMethod: checkout.paymentMethod,
            checkoutKey: `${checkout.id}:${checkout.nonce}`,
            items: {
              create: {
                productId: product.id,
                productName: product.name,
                setNumber: product.setNumber,
                theme: product.theme,
                condition: product.condition,
                unitPrice: product.price,
                quantity: checkout.quantity,
                lineTotal,
              },
            },
          },
        });

        const levels = await this.inventory.reserve(
          tx,
          { productId: product.id, quantity: checkout.quantity },
          created.id,
          { actorType: "CUSTOMER" },
        );

        await tx.orderStatusHistory.create({
          data: { orderId: created.id, fromStatus: null, toStatus: "NEW", actorType: "CUSTOMER", note: "Оформлено покупцем" },
        });
        await tx.checkout.update({
          where: { id: checkout.id },
          data: { status: "SUBMITTED", orderId: created.id, step: "SUMMARY", editingField: null },
        });
        await tx.customer.update({
          where: { id: checkout.customerId },
          data: {
            fullName: checkout.fullName,
            phone: checkout.phone,
            city: checkout.city,
            deliveryPoint: checkout.deliveryPoint,
            lastOrderAt: new Date(),
          },
        });

        const order = await tx.order.findUniqueOrThrow({ where: { id: created.id }, include: ORDER_INCLUDE });
        const stock: StockSnapshot[] = [
          { productId: product.id, ...levels, lowStockThreshold: product.lowStockThreshold },
        ];
        await this.notifier.orderCreated(tx, order, stock);
        return { kind: "created", order } as const;
      });
    } catch (err) {
      // Запасний захист: якщо умовний UPDATE не пройшов, транзакцію вже відкочено.
      if (err instanceof InsufficientStockError) return { kind: "insufficient_stock", available: err.available };
      throw err;
    }
  }

  /**
   * Змінює статус замовлення. Складські операції виконуються за полем stockState,
   * тому повторні чи «перестрибуючі» зміни статусу не списують товар двічі.
   */
  async changeStatus(params: {
    orderId: number;
    to: OrderStatus;
    actor: OrderActor;
    note?: string | null;
    trackingNumber?: string | null;
  }): Promise<{ changed: boolean; order: OrderFull }> {
    return inTransaction(this.prisma, async (tx) => {
      const order = await this.lockOrder(tx, params.orderId);
      const from = order.status;
      if (from === params.to) return { changed: false, order };
      if (!canTransition(from, params.to)) {
        throw new InvalidTransitionError(
          `Неможливо змінити статус замовлення №${order.id} з «${ORDER_STATUS_LABELS[from]}» на «${ORDER_STATUS_LABELS[params.to]}»`,
        );
      }
      const actor = { actorType: params.actor.actorType, actorTelegramId: params.actor.actorTelegramId ?? null };
      const items = sortedItems(order);
      let stockState: StockState = order.stockState;

      if ((params.to === "SHIPPED" || params.to === "DELIVERED") && stockState === "RESERVED") {
        for (const item of items) {
          await this.inventory.ship(tx, { productId: item.productId, quantity: item.quantity }, order.id, actor);
        }
        stockState = "SHIPPED";
      }
      if (params.to === "CANCELED") {
        if (stockState === "RESERVED") {
          for (const item of items) {
            await this.inventory.release(tx, { productId: item.productId, quantity: item.quantity }, order.id, actor);
          }
          stockState = "RELEASED";
        } else {
          throw new InvalidTransitionError("Відправлене замовлення не можна скасувати — оформіть повернення");
        }
      }
      if (params.to === "RETURNED" && stockState !== "SHIPPED") {
        throw new InvalidTransitionError("Повернення можливе лише для відправленого товару");
      }

      const data: Prisma.OrderUpdateInput = { status: params.to, stockState };
      const tsField = STATUS_TIMESTAMP[params.to];
      if (tsField) (data as Record<string, unknown>)[tsField] = new Date();
      if (params.trackingNumber) data.trackingNumber = params.trackingNumber;
      await tx.order.update({ where: { id: order.id }, data });

      // Сума завершених покупок: зараховується при доставці, сторнується при поверненні.
      if (params.to === "DELIVERED") {
        await tx.customer.update({
          where: { id: order.customerId },
          data: { totalSpent: { increment: order.totalAmount } },
        });
      }
      if (from === "DELIVERED" && params.to === "RETURNED") {
        await tx.$executeRaw`
          UPDATE customers SET total_spent = GREATEST(0, total_spent - ${order.totalAmount}), updated_at = NOW()
          WHERE id = ${order.customerId}`;
      }

      const history = await tx.orderStatusHistory.create({
        data: {
          orderId: order.id,
          fromStatus: from,
          toStatus: params.to,
          actorType: actor.actorType,
          actorTelegramId: actor.actorTelegramId,
          note: params.note ?? null,
        },
      });
      const updated = await tx.order.findUniqueOrThrow({ where: { id: order.id }, include: ORDER_INCLUDE });
      await this.notifier.statusChanged(tx, updated, params.to, history.id, params.note);
      return { changed: true, order: updated };
    });
  }

  /**
   * Завершує повернення після фактичного отримання товару власником:
   * restock=true — товар повертається на склад, false — не повертається (брак).
   */
  async resolveReturn(params: { orderId: number; restock: boolean; actorTelegramId: bigint }): Promise<OrderFull> {
    return inTransaction(this.prisma, async (tx) => {
      const order = await this.lockOrder(tx, params.orderId);
      if (order.status !== "RETURNED") throw new InvalidTransitionError("Замовлення не має статусу «повернення»");
      if (order.stockState !== "SHIPPED") throw new InvalidTransitionError("Повернення за цим замовленням уже оброблено");
      const actor = { actorType: "ADMIN" as const, actorTelegramId: params.actorTelegramId };
      if (params.restock) {
        for (const item of sortedItems(order)) {
          await this.inventory.restockReturn(tx, { productId: item.productId, quantity: item.quantity }, order.id, actor);
        }
      }
      await tx.order.update({
        where: { id: order.id },
        data: { stockState: params.restock ? "RESTOCKED" : "WRITTEN_OFF", returnResolvedAt: new Date() },
      });
      await tx.orderStatusHistory.create({
        data: {
          orderId: order.id,
          fromStatus: "RETURNED",
          toStatus: "RETURNED",
          actorType: "ADMIN",
          actorTelegramId: params.actorTelegramId,
          note: params.restock ? "Товар фактично повернуто на склад" : "Повернення без повернення на склад (брак)",
        },
      });
      const updated = await tx.order.findUniqueOrThrow({ where: { id: order.id }, include: ORDER_INCLUDE });
      await this.notifier.returnResolved(tx, updated);
      return updated;
    });
  }

  /** Після того як магазин отримав сповіщення: «нове» → «очікує підтвердження магазину». */
  async markAwaitingConfirmation(orderId: number): Promise<boolean> {
    return inTransaction(this.prisma, async (tx) => {
      const res = await tx.order.updateMany({
        where: { id: orderId, status: "NEW" },
        data: { status: "AWAITING_CONFIRMATION" },
      });
      if (res.count === 0) return false;
      await tx.orderStatusHistory.create({
        data: {
          orderId,
          fromStatus: "NEW",
          toStatus: "AWAITING_CONFIRMATION",
          actorType: "SYSTEM",
          note: "Магазин отримав сповіщення",
        },
      });
      return true;
    });
  }

  async setTrackingNumber(orderId: number, trackingNumber: string): Promise<void> {
    await this.prisma.order.update({ where: { id: orderId }, data: { trackingNumber } });
  }

  async getOrder(id: number): Promise<OrderWithHistory | null> {
    return this.prisma.order.findUnique({
      where: { id },
      include: { items: true, customer: true, history: { orderBy: { createdAt: "asc" } } },
    });
  }

  async getOrderForCustomer(id: number, customerId: number): Promise<OrderFull | null> {
    return this.prisma.order.findFirst({ where: { id, customerId }, include: ORDER_INCLUDE });
  }

  async listOrders(filter: OrderListFilter, limit: number, offset: number) {
    const statuses = ORDER_FILTER_STATUSES[filter];
    const where: Prisma.OrderWhereInput = statuses ? { status: { in: statuses } } : {};
    const [items, total] = await Promise.all([
      this.prisma.order.findMany({
        where,
        include: ORDER_INCLUDE,
        orderBy: { createdAt: "desc" },
        take: limit,
        skip: offset,
      }),
      this.prisma.order.count({ where }),
    ]);
    return { items, total };
  }

  async customerOrders(customerId: number, limit = 10): Promise<OrderFull[]> {
    return this.prisma.order.findMany({
      where: { customerId },
      include: ORDER_INCLUDE,
      orderBy: { createdAt: "desc" },
      take: limit,
    });
  }

  private async lockOrder(tx: Tx, orderId: number): Promise<OrderFull> {
    const rows = await tx.$queryRaw<Array<{ id: number }>>`SELECT id FROM orders WHERE id = ${orderId} FOR UPDATE`;
    if (rows.length === 0) throw new NotFoundError(`Замовлення №${orderId} не знайдено`);
    return tx.order.findUniqueOrThrow({ where: { id: orderId }, include: ORDER_INCLUDE });
  }

  /** Залишки товарів після операції — для повідомлень адміністратору. */
  static levelsText(levels: StockLevels): string {
    return `доступно ${levels.available} (на складі ${levels.onHand}, у резерві ${levels.reserved})`;
  }
}

/** Товари замовлення в порядку зростання id — однаковий порядок блокування рядків у всіх транзакціях. */
function sortedItems(order: OrderFull): OrderFull["items"] {
  return [...order.items].sort((a, b) => a.productId - b.productId);
}

type CompleteCheckout = Checkout & {
  productId: number;
  quantity: number;
  fullName: string;
  phone: string;
  city: string;
  deliveryPoint: string;
  paymentMethod: NonNullable<Checkout["paymentMethod"]>;
};

export function isComplete(c: Checkout): c is CompleteCheckout {
  return (
    c.productId !== null &&
    c.quantity !== null &&
    c.quantity > 0 &&
    Boolean(c.fullName) &&
    Boolean(c.phone) &&
    Boolean(c.city) &&
    Boolean(c.deliveryPoint) &&
    c.paymentMethod !== null
  );
}

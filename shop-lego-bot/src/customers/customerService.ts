import type { Customer } from "../generated/prisma/client.js";
import { inTransaction, type PrismaClient } from "../database/client.js";
import { productTitle } from "../catalog/productPresenter.js";
import { ACTIVE_ORDER_STATUSES } from "../orders/orderStatus.js";

export interface TelegramUserLike {
  id: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  language_code?: string;
}

export interface PurchasedSet {
  productId: number;
  title: string;
  setNumber: string | null;
  lastOrderId: number;
  lastOrderedAt: Date;
  quantity: number;
}

export interface CustomerProfile {
  customer: Customer;
  ordersCount: number;
  completedCount: number;
  purchasedSets: PurchasedSet[];
}

const SEEN_UPDATE_INTERVAL_MS = 10 * 60_000;

export class CustomerService {
  constructor(private readonly prisma: PrismaClient) {}

  /** Створює або оновлює покупця за даними Telegram (ID, ім'я користувача). */
  async upsertFromTelegram(user: TelegramUserLike): Promise<Customer> {
    const telegramId = BigInt(user.id);
    const existing = await this.prisma.customer.findUnique({ where: { telegramId } });
    const profile = {
      username: user.username ?? null,
      firstName: user.first_name ?? null,
      lastName: user.last_name ?? null,
      languageCode: user.language_code ?? null,
    };
    if (!existing) {
      return this.prisma.customer.upsert({
        where: { telegramId },
        create: { telegramId, ...profile },
        update: { ...profile, lastSeenAt: new Date() },
      });
    }
    // Після /forgetme дані профілю Telegram більше не зберігаємо.
    const keepAnonymous = existing.anonymizedAt !== null;
    const changed =
      !keepAnonymous &&
      (existing.username !== profile.username ||
        existing.firstName !== profile.firstName ||
        existing.lastName !== profile.lastName ||
        existing.languageCode !== profile.languageCode);
    const stale = Date.now() - existing.lastSeenAt.getTime() > SEEN_UPDATE_INTERVAL_MS;
    if (!changed && !stale && !existing.isBlocked) return existing;
    return this.prisma.customer.update({
      where: { id: existing.id },
      data: {
        ...(keepAnonymous ? {} : profile),
        lastSeenAt: new Date(),
        isBlocked: false,
      },
    });
  }

  async getById(id: number): Promise<Customer | null> {
    return this.prisma.customer.findUnique({ where: { id } });
  }

  async getByTelegramId(telegramId: bigint): Promise<Customer | null> {
    return this.prisma.customer.findUnique({ where: { telegramId } });
  }

  /** Історія покупок: які набори покупець замовляв (крім скасованих замовлень). */
  async purchasedSets(customerId: number, limit = 10): Promise<PurchasedSet[]> {
    const items = await this.prisma.orderItem.findMany({
      where: { order: { customerId, status: { not: "CANCELED" } } },
      include: { order: { select: { id: true, createdAt: true } } },
      orderBy: { order: { createdAt: "desc" } },
      take: 100,
    });
    const byProduct = new Map<number, PurchasedSet>();
    for (const item of items) {
      const existing = byProduct.get(item.productId);
      if (existing) {
        existing.quantity += item.quantity;
        continue;
      }
      byProduct.set(item.productId, {
        productId: item.productId,
        title: productTitle({ theme: item.theme, setNumber: item.setNumber, name: item.productName }),
        setNumber: item.setNumber,
        lastOrderId: item.order.id,
        lastOrderedAt: item.order.createdAt,
        quantity: item.quantity,
      });
    }
    return [...byProduct.values()].slice(0, limit);
  }

  async profile(customerId: number): Promise<CustomerProfile | null> {
    const customer = await this.getById(customerId);
    if (!customer) return null;
    const [ordersCount, completedCount, purchasedSets] = await Promise.all([
      this.prisma.order.count({ where: { customerId } }),
      this.prisma.order.count({ where: { customerId, status: "DELIVERED" } }),
      this.purchasedSets(customerId),
    ]);
    return { customer, ordersCount, completedCount, purchasedSets };
  }

  /** Чи є збережені дані доставки з попереднього замовлення. */
  hasSavedProfile(c: Customer): boolean {
    return Boolean(c.fullName && c.phone && c.city && c.deliveryPoint);
  }

  async setMarketingOptOut(customerId: number, optOut: boolean): Promise<void> {
    await this.prisma.customer.update({ where: { id: customerId }, data: { marketingOptOut: optOut } });
  }

  async markBlockedByTelegramId(telegramId: bigint, blocked: boolean): Promise<void> {
    await this.prisma.customer.updateMany({ where: { telegramId }, data: { isBlocked: blocked } });
  }

  async activeOrderIds(customerId: number): Promise<number[]> {
    const orders = await this.prisma.order.findMany({
      where: { customerId, status: { in: ACTIVE_ORDER_STATUSES } },
      select: { id: true },
      orderBy: { id: "asc" },
    });
    return orders.map((o) => o.id);
  }

  /**
   * Видалення персональних даних на вимогу покупця (/forgetme).
   * Замовлення залишаються для обліку, але ім'я, телефон і адреса в них знеособлюються.
   * Недоступно, поки є незавершені замовлення (дані потрібні для доставки).
   */
  async forget(customerId: number): Promise<{ ok: true } | { ok: false; activeOrderIds: number[] }> {
    const activeOrderIds = await this.activeOrderIds(customerId);
    if (activeOrderIds.length > 0) return { ok: false, activeOrderIds };
    await inTransaction(this.prisma, async (tx) => {
      await tx.customer.update({
        where: { id: customerId },
        data: {
          username: null,
          firstName: null,
          lastName: null,
          fullName: null,
          phone: null,
          city: null,
          deliveryPoint: null,
          marketingOptOut: true,
          anonymizedAt: new Date(),
        },
      });
      await tx.order.updateMany({
        where: { customerId },
        data: { fullName: "Дані видалено на вимогу покупця", phone: "—", city: "—", deliveryPoint: "—" },
      });
      await tx.chatMessage.deleteMany({ where: { customerId } });
      await tx.checkout.deleteMany({ where: { customerId } });
    });
    return { ok: true };
  }

  async list(limit: number, offset: number) {
    const [items, total] = await Promise.all([
      this.prisma.customer.findMany({
        orderBy: [{ lastOrderAt: { sort: "desc", nulls: "last" } }, { createdAt: "desc" }],
        take: limit,
        skip: offset,
        include: { _count: { select: { orders: true } } },
      }),
      this.prisma.customer.count(),
    ]);
    return { items, total };
  }
}

import type { ActorType, StockMovementType } from "../generated/prisma/client.js";
import { inTransaction, type PrismaClient, type Tx } from "../database/client.js";
import { InsufficientStockError, InventoryInvariantError, NotFoundError, ValidationError } from "../lib/errors.js";

export interface StockActor {
  actorType: ActorType;
  actorTelegramId?: bigint | null;
}

export interface StockLine {
  productId: number;
  quantity: number;
}

interface StockRow {
  stock_on_hand: number;
  stock_reserved: number;
}

export interface StockLevels {
  onHand: number;
  reserved: number;
  available: number;
}

/**
 * Облік складу. Усі зміни виконуються атомарними умовними UPDATE у транзакції:
 * умова в WHERE перевіряється PostgreSQL після блокування рядка, тому два одночасні
 * замовлення на останній набір не можуть обидва пройти. Додатково CHECK-обмеження
 * в БД забороняють від'ємні залишки та резерв більший за фізичну кількість.
 *
 * Модель:  на складі (onHand)  −  у резерві (reserved)  =  доступно покупцям.
 *  - підтвердження замовлення покупцем: reserved += q   (доступно зменшується)
 *  - скасування до відправлення:        reserved −= q   (доступно повертається)
 *  - відправлення:                      onHand −= q, reserved −= q
 *  - підтверджене повернення:           onHand += q
 */
export class InventoryService {
  constructor(private readonly prisma: PrismaClient) {}

  private async log(
    tx: Tx,
    params: {
      productId: number;
      type: StockMovementType;
      onHandDelta: number;
      reservedDelta: number;
      after: StockRow;
      orderId?: number | null;
      actor: StockActor;
      note?: string | null;
    },
  ): Promise<void> {
    await tx.stockMovement.create({
      data: {
        productId: params.productId,
        type: params.type,
        onHandDelta: params.onHandDelta,
        reservedDelta: params.reservedDelta,
        onHandAfter: params.after.stock_on_hand,
        reservedAfter: params.after.stock_reserved,
        orderId: params.orderId ?? null,
        actorType: params.actor.actorType,
        actorTelegramId: params.actor.actorTelegramId ?? null,
        note: params.note ?? null,
      },
    });
  }

  private static assertQuantity(quantity: number): void {
    if (!Number.isInteger(quantity) || quantity <= 0) {
      throw new ValidationError("Кількість має бути цілим додатним числом");
    }
  }

  private static async currentAvailable(tx: Tx, productId: number): Promise<number> {
    const p = await tx.product.findUnique({ where: { id: productId } });
    if (!p || p.status !== "ACTIVE") return 0;
    return Math.max(0, p.stockOnHand - p.stockReserved);
  }

  /** Резервує товар під замовлення. Кидає InsufficientStockError, якщо доступно менше. */
  async reserve(tx: Tx, line: StockLine, orderId: number, actor: StockActor): Promise<StockLevels> {
    InventoryService.assertQuantity(line.quantity);
    const rows = await tx.$queryRaw<StockRow[]>`
      UPDATE products
      SET stock_reserved = stock_reserved + ${line.quantity}, updated_at = NOW()
      WHERE id = ${line.productId}
        AND status = 'ACTIVE'
        AND stock_on_hand - stock_reserved >= ${line.quantity}
      RETURNING stock_on_hand, stock_reserved`;
    const after = rows[0];
    if (!after) {
      throw new InsufficientStockError(
        line.productId,
        line.quantity,
        await InventoryService.currentAvailable(tx, line.productId),
      );
    }
    await this.log(tx, {
      productId: line.productId,
      type: "ORDER_RESERVE",
      onHandDelta: 0,
      reservedDelta: line.quantity,
      after,
      orderId,
      actor,
      note: `Резерв під замовлення №${orderId}`,
    });
    return toLevels(after);
  }

  /** Знімає резерв (скасування до відправлення) — товар знову доступний покупцям. */
  async release(tx: Tx, line: StockLine, orderId: number, actor: StockActor): Promise<StockLevels> {
    InventoryService.assertQuantity(line.quantity);
    const rows = await tx.$queryRaw<StockRow[]>`
      UPDATE products
      SET stock_reserved = stock_reserved - ${line.quantity}, updated_at = NOW()
      WHERE id = ${line.productId} AND stock_reserved >= ${line.quantity}
      RETURNING stock_on_hand, stock_reserved`;
    const after = rows[0];
    if (!after) {
      throw new InventoryInvariantError(
        `Неможливо зняти резерв ${line.quantity} шт. для товару #${line.productId} (замовлення №${orderId})`,
      );
    }
    await this.log(tx, {
      productId: line.productId,
      type: "ORDER_RELEASE",
      onHandDelta: 0,
      reservedDelta: -line.quantity,
      after,
      orderId,
      actor,
      note: `Скасування замовлення №${orderId}: резерв знято`,
    });
    return toLevels(after);
  }

  /** Відвантаження: товар фізично залишає склад (списується із залишку й резерву). */
  async ship(tx: Tx, line: StockLine, orderId: number, actor: StockActor): Promise<StockLevels> {
    InventoryService.assertQuantity(line.quantity);
    const rows = await tx.$queryRaw<StockRow[]>`
      UPDATE products
      SET stock_on_hand = stock_on_hand - ${line.quantity},
          stock_reserved = stock_reserved - ${line.quantity},
          updated_at = NOW()
      WHERE id = ${line.productId}
        AND stock_reserved >= ${line.quantity}
        AND stock_on_hand >= ${line.quantity}
      RETURNING stock_on_hand, stock_reserved`;
    const after = rows[0];
    if (!after) {
      throw new InventoryInvariantError(
        `Неможливо списати ${line.quantity} шт. товару #${line.productId} (замовлення №${orderId}): резерв відсутній`,
      );
    }
    await this.log(tx, {
      productId: line.productId,
      type: "ORDER_SHIP",
      onHandDelta: -line.quantity,
      reservedDelta: -line.quantity,
      after,
      orderId,
      actor,
      note: `Відправлено за замовленням №${orderId}`,
    });
    return toLevels(after);
  }

  /** Повернення товару на склад після того, як власник підтвердив фактичне повернення. */
  async restockReturn(tx: Tx, line: StockLine, orderId: number, actor: StockActor): Promise<StockLevels> {
    InventoryService.assertQuantity(line.quantity);
    const rows = await tx.$queryRaw<StockRow[]>`
      UPDATE products
      SET stock_on_hand = stock_on_hand + ${line.quantity}, updated_at = NOW()
      WHERE id = ${line.productId}
      RETURNING stock_on_hand, stock_reserved`;
    const after = rows[0];
    if (!after) throw new NotFoundError(`Товар #${line.productId} не знайдено`);
    await this.log(tx, {
      productId: line.productId,
      type: "RETURN_RESTOCK",
      onHandDelta: line.quantity,
      reservedDelta: 0,
      after,
      orderId,
      actor,
      note: `Повернення за замовленням №${orderId}`,
    });
    return toLevels(after);
  }

  /** Надходження товару на склад (/addstock). */
  async addStock(productId: number, quantity: number, actorTelegramId: bigint, note?: string): Promise<StockLevels> {
    InventoryService.assertQuantity(quantity);
    return inTransaction(this.prisma, async (tx) => {
      const rows = await tx.$queryRaw<StockRow[]>`
        UPDATE products
        SET stock_on_hand = stock_on_hand + ${quantity}, updated_at = NOW()
        WHERE id = ${productId}
        RETURNING stock_on_hand, stock_reserved`;
      const after = rows[0];
      if (!after) throw new NotFoundError(`Товар #${productId} не знайдено`);
      await this.log(tx, {
        productId,
        type: "RESTOCK",
        onHandDelta: quantity,
        reservedDelta: 0,
        after,
        actor: { actorType: "ADMIN", actorTelegramId },
        note: note ?? "Надходження на склад",
      });
      return toLevels(after);
    });
  }

  /**
   * Ручне коригування залишку (інвентаризація, брак, списання).
   * Зменшити можна лише вільний (не зарезервований) товар.
   */
  async adjustStock(productId: number, delta: number, actorTelegramId: bigint, note: string): Promise<StockLevels> {
    if (!Number.isInteger(delta) || delta === 0) throw new ValidationError("Зміна має бути цілим ненульовим числом");
    return inTransaction(this.prisma, async (tx) => {
      const rows = await tx.$queryRaw<StockRow[]>`
        UPDATE products
        SET stock_on_hand = stock_on_hand + ${delta}, updated_at = NOW()
        WHERE id = ${productId} AND stock_on_hand + ${delta} >= stock_reserved
        RETURNING stock_on_hand, stock_reserved`;
      const after = rows[0];
      if (!after) {
        const p = await tx.product.findUnique({ where: { id: productId } });
        if (!p) throw new NotFoundError(`Товар #${productId} не знайдено`);
        const free = Math.max(0, p.stockOnHand - p.stockReserved);
        throw new ValidationError(
          `Неможливо зменшити залишок на ${Math.abs(delta)}: на складі ${p.stockOnHand}, ` +
            `з них зарезервовано під замовлення ${p.stockReserved}. Можна списати не більше ${free}.`,
        );
      }
      await this.log(tx, {
        productId,
        type: "ADJUSTMENT",
        onHandDelta: delta,
        reservedDelta: 0,
        after,
        actor: { actorType: "ADMIN", actorTelegramId },
        note,
      });
      return toLevels(after);
    });
  }

  async levels(productId: number): Promise<StockLevels> {
    const p = await this.prisma.product.findUnique({ where: { id: productId } });
    if (!p) throw new NotFoundError(`Товар #${productId} не знайдено`);
    return { onHand: p.stockOnHand, reserved: p.stockReserved, available: Math.max(0, p.stockOnHand - p.stockReserved) };
  }

  async movements(productId: number, limit = 20) {
    return this.prisma.stockMovement.findMany({
      where: { productId },
      orderBy: [{ createdAt: "desc" }, { id: "desc" }],
      take: limit,
    });
  }
}

function toLevels(row: StockRow): StockLevels {
  return {
    onHand: row.stock_on_hand,
    reserved: row.stock_reserved,
    available: Math.max(0, row.stock_on_hand - row.stock_reserved),
  };
}

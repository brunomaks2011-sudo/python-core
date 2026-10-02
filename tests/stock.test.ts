import { describe, expect, it } from "vitest";
import { decrementStock, InsufficientStockError, restoreStock, type StockTx } from "@/lib/orders/stock";

/** Імітація таблиці товарів з тією ж семантикою умовного UPDATE, що й у PostgreSQL. */
function fakeTx(initial: Record<string, { stock: number; isActive?: boolean }>) {
  const db = Object.fromEntries(
    Object.entries(initial).map(([id, p]) => [id, { stock: p.stock, isActive: p.isActive ?? true, salesCount: 0 }]),
  );
  const tx: StockTx = {
    product: {
      async updateMany({ where, data }) {
        const row = db[where.id];
        if (!row) return { count: 0 };
        if (where.isActive !== undefined && row.isActive !== where.isActive) return { count: 0 };
        if (where.stock && row.stock < where.stock.gte) return { count: 0 };
        if ("decrement" in data.stock) row.stock -= data.stock.decrement;
        else row.stock += data.stock.increment;
        if (data.salesCount && "increment" in data.salesCount) row.salesCount += data.salesCount.increment;
        if (data.salesCount && "decrement" in data.salesCount) row.salesCount -= data.salesCount.decrement;
        return { count: 1 };
      },
      async findUnique({ where }) {
        return db[where.id] ? { stock: db[where.id].stock } : null;
      },
    },
  };
  return { tx, db };
}

describe("списання залишків", () => {
  it("зменшує залишок і збільшує лічильник продажів", async () => {
    const { tx, db } = fakeTx({ a: { stock: 5 }, b: { stock: 1 } });
    await decrementStock(tx, [
      { productId: "a", quantity: 2, name: "A" },
      { productId: "b", quantity: 1, name: "B" },
    ]);
    expect(db.a.stock).toBe(3);
    expect(db.b.stock).toBe(0);
    expect(db.a.salesCount).toBe(2);
  });

  it("не дозволяє купити більше, ніж є на складі", async () => {
    const { tx, db } = fakeTx({ a: { stock: 2 } });
    const err = await decrementStock(tx, [{ productId: "a", quantity: 3, name: "Замок" }]).catch((e) => e);
    expect(err).toBeInstanceOf(InsufficientStockError);
    expect(err.available).toBe(2);
    expect(err.message).toContain("доступно лише 2");
    expect(db.a.stock).toBe(2);
  });

  it("не продає прихований товар", async () => {
    const { tx } = fakeTx({ a: { stock: 10, isActive: false } });
    await expect(decrementStock(tx, [{ productId: "a", quantity: 1, name: "A" }])).rejects.toBeInstanceOf(InsufficientStockError);
  });

  it("відхиляє нульову або від'ємну кількість", async () => {
    const { tx } = fakeTx({ a: { stock: 10 } });
    await expect(decrementStock(tx, [{ productId: "a", quantity: 0, name: "A" }])).rejects.toThrow();
    await expect(decrementStock(tx, [{ productId: "a", quantity: -2, name: "A" }])).rejects.toThrow();
  });

  it("другий покупець не може купити останню одиницю", async () => {
    const { tx, db } = fakeTx({ a: { stock: 1 } });
    await decrementStock(tx, [{ productId: "a", quantity: 1, name: "A" }]);
    await expect(decrementStock(tx, [{ productId: "a", quantity: 1, name: "A" }])).rejects.toBeInstanceOf(InsufficientStockError);
    expect(db.a.stock).toBe(0);
  });

  it("повертає залишки при скасуванні", async () => {
    const { tx, db } = fakeTx({ a: { stock: 0 } });
    await restoreStock(tx, [{ productId: "a", quantity: 3 }, { productId: null, quantity: 5 }]);
    expect(db.a.stock).toBe(3);
  });
});

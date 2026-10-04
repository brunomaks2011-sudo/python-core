/**
 * Інтеграційний тест списання залишків на справжній PostgreSQL.
 * Запуск: RUN_DB_TESTS=1 npm test  (потрібна база з DATABASE_URL і застосовані міграції)
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { PrismaClient } from "@prisma/client";
import { decrementStock, InsufficientStockError } from "@/lib/orders/stock";

const enabled = process.env.RUN_DB_TESTS === "1";

describe.skipIf(!enabled)("списання залишків у PostgreSQL", () => {
  const prisma = new PrismaClient();
  const tag = `test-${Date.now()}`;
  let productId = "";
  let categoryId = "";

  beforeAll(async () => {
    const c = await prisma.category.create({ data: { name: tag, slug: tag } });
    categoryId = c.id;
    const p = await prisma.product.create({
      data: { name: tag, slug: tag, sku: tag, description: "", price: 1000, stock: 3, pieces: 1, ageMin: 1, categoryId },
    });
    productId = p.id;
  });

  afterAll(async () => {
    await prisma.product.deleteMany({ where: { categoryId } });
    await prisma.category.delete({ where: { id: categoryId } });
    await prisma.$disconnect();
  });

  it("10 паралельних покупців не можуть купити більше 3 одиниць", async () => {
    const results = await Promise.allSettled(
      Array.from({ length: 10 }, () =>
        prisma.$transaction((tx) => decrementStock(tx, [{ productId, quantity: 1, name: tag }])),
      ),
    );
    const ok = results.filter((r) => r.status === "fulfilled").length;
    const rejected = results.filter((r) => r.status === "rejected");
    expect(ok).toBe(3);
    expect(rejected).toHaveLength(7);
    for (const r of rejected) expect((r as PromiseRejectedResult).reason).toBeInstanceOf(InsufficientStockError);
    const p = await prisma.product.findUniqueOrThrow({ where: { id: productId } });
    expect(p.stock).toBe(0);
    expect(p.salesCount).toBe(3);
  });

  it("при нестачі одного товару транзакція відкочує всі списання", async () => {
    await prisma.product.update({ where: { id: productId }, data: { stock: 5 } });
    const other = await prisma.product.create({
      data: { name: `${tag}-2`, slug: `${tag}-2`, sku: `${tag}-2`, description: "", price: 1, stock: 0, pieces: 1, ageMin: 1, categoryId },
    });
    await expect(
      prisma.$transaction((tx) =>
        decrementStock(tx, [
          { productId, quantity: 2, name: tag },
          { productId: other.id, quantity: 1, name: "other" },
        ]),
      ),
    ).rejects.toBeInstanceOf(InsufficientStockError);
    const p = await prisma.product.findUniqueOrThrow({ where: { id: productId } });
    expect(p.stock).toBe(5);
  });
});

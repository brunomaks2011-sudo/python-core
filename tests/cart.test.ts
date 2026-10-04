import { describe, expect, it } from "vitest";
import {
  applyFreeShipping,
  clampQuantity,
  computeCartTotals,
  computeOrderTotal,
  mergeCartLines,
} from "@/lib/cart/calc";

const line = (o: Partial<Parameters<typeof computeCartTotals>[0][number]> = {}) => ({
  productId: "p1",
  quantity: 1,
  unitPrice: 10000,
  stock: 10,
  isActive: true,
  ...o,
});

describe("розрахунок суми кошика", () => {
  it("порожній кошик", () => {
    expect(computeCartTotals([])).toEqual({ itemsCount: 0, itemsTotal: 0, hasUnavailable: false });
  });

  it("сумує позиції в копійках", () => {
    const t = computeCartTotals([
      line({ productId: "a", quantity: 2, unitPrice: 129900 }),
      line({ productId: "b", quantity: 3, unitPrice: 34999 }),
    ]);
    expect(t.itemsCount).toBe(5);
    expect(t.itemsTotal).toBe(2 * 129900 + 3 * 34999);
    expect(t.hasUnavailable).toBe(false);
  });

  it("не рахує більше, ніж є на складі, і позначає це", () => {
    const t = computeCartTotals([line({ quantity: 5, stock: 2, unitPrice: 1000 })]);
    expect(t.itemsCount).toBe(2);
    expect(t.itemsTotal).toBe(2000);
    expect(t.hasUnavailable).toBe(true);
  });

  it("не рахує приховані товари", () => {
    const t = computeCartTotals([line({ isActive: false }), line({ productId: "x", unitPrice: 500 })]);
    expect(t.itemsTotal).toBe(500);
    expect(t.hasUnavailable).toBe(true);
  });

  it("відхиляє дробові ціни (гроші — лише цілі копійки)", () => {
    expect(() => computeCartTotals([line({ unitPrice: 10.5 })])).toThrow();
  });

  it("загальна сума = товари + доставка", () => {
    expect(computeOrderTotal(250000, 8000)).toBe(258000);
  });
});

describe("кількість", () => {
  it("обмежує залишком і максимумом 99", () => {
    expect(clampQuantity(5, 3)).toBe(3);
    expect(clampQuantity(500, 1000)).toBe(99);
    expect(clampQuantity(-1, 10)).toBe(0);
    expect(clampQuantity(2.7, 10)).toBe(2);
    expect(clampQuantity(Number.NaN, 10)).toBe(0);
  });
});

describe("безкоштовна доставка", () => {
  it("безкоштовно від порогу включно", () => {
    expect(applyFreeShipping(200000, 8000, 200000)).toEqual({ cost: 0, free: true });
  });
  it("платно нижче порогу", () => {
    expect(applyFreeShipping(199999, 8000, 200000)).toEqual({ cost: 8000, free: false });
  });
  it("поріг 0 вимикає безкоштовну доставку", () => {
    expect(applyFreeShipping(10_000_000, 8000, 0)).toEqual({ cost: 8000, free: false });
  });
});

describe("об'єднання кошиків після входу", () => {
  it("сумує однакові товари з урахуванням залишку", () => {
    const stock: Record<string, number> = { a: 3, b: 10, c: 0 };
    const merged = mergeCartLines(
      [{ productId: "a", quantity: 2 }, { productId: "b", quantity: 1 }],
      [{ productId: "a", quantity: 2 }, { productId: "c", quantity: 1 }],
      (id) => stock[id],
    );
    expect(merged).toEqual([
      { productId: "a", quantity: 3 },
      { productId: "b", quantity: 1 },
    ]);
  });
});

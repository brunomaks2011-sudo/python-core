// Чиста (без БД) логіка кошика — легко тестується.

export const MAX_QTY_PER_ITEM = 99;

export type CartLineInput = {
  productId: string;
  quantity: number;
  unitPrice: number; // копійки
  stock: number;
  isActive: boolean;
};

export type CartTotals = {
  itemsCount: number;
  itemsTotal: number; // копійки
  hasUnavailable: boolean;
};

/** Обмежує кількість діапазоном [0, min(stock, MAX_QTY_PER_ITEM)]. */
export function clampQuantity(quantity: number, stock: number): number {
  if (!Number.isFinite(quantity)) return 0;
  const max = Math.max(0, Math.min(stock, MAX_QTY_PER_ITEM));
  return Math.max(0, Math.min(Math.trunc(quantity), max));
}

/** Сума тільки за доступні позиції (активні та в межах залишку). */
export function computeCartTotals(lines: CartLineInput[]): CartTotals {
  let itemsCount = 0;
  let itemsTotal = 0;
  let hasUnavailable = false;
  for (const line of lines) {
    if (!Number.isInteger(line.unitPrice) || line.unitPrice < 0) throw new Error("Ціна має бути цілим числом у копійках");
    const available = line.isActive ? clampQuantity(line.quantity, line.stock) : 0;
    if (available < line.quantity) hasUnavailable = true;
    itemsCount += available;
    itemsTotal += available * line.unitPrice;
  }
  return { itemsCount, itemsTotal, hasUnavailable };
}

export type DeliveryInfo = { cost: number; free: boolean };

/** Безкоштовна доставка, якщо сума товарів ≥ порогу (поріг 0 = вимкнено). */
export function applyFreeShipping(itemsTotal: number, baseCost: number, threshold: number): DeliveryInfo {
  if (threshold > 0 && itemsTotal >= threshold) return { cost: 0, free: true };
  return { cost: Math.max(0, Math.round(baseCost)), free: baseCost === 0 };
}

export function computeOrderTotal(itemsTotal: number, deliveryCost: number): number {
  return itemsTotal + deliveryCost;
}

/**
 * Об'єднання гостьового кошика з кошиком користувача після входу:
 * кількості однакових товарів сумуються, але не перевищують залишок.
 */
export function mergeCartLines(
  userLines: { productId: string; quantity: number }[],
  guestLines: { productId: string; quantity: number }[],
  stockOf: (productId: string) => number,
): { productId: string; quantity: number }[] {
  const merged = new Map<string, number>();
  for (const l of [...userLines, ...guestLines]) merged.set(l.productId, (merged.get(l.productId) ?? 0) + l.quantity);
  return [...merged.entries()]
    .map(([productId, q]) => ({ productId, quantity: clampQuantity(q, stockOf(productId)) }))
    .filter((l) => l.quantity > 0);
}

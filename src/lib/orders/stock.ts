// Списання та повернення залишків. Викликається всередині транзакції Prisma.

export class InsufficientStockError extends Error {
  constructor(
    public readonly productId: string,
    public readonly productName: string,
    public readonly available: number,
  ) {
    super(
      available > 0
        ? `«${productName}»: доступно лише ${available} шт.`
        : `«${productName}» вже немає в наявності`,
    );
    this.name = "InsufficientStockError";
  }
}

export type StockLine = { productId: string; quantity: number; name: string };

/** Мінімальний інтерфейс транзакційного клієнта, потрібний для роботи із залишками. */
export type StockTx = {
  product: {
    updateMany(args: {
      where: { id: string; isActive?: boolean; stock?: { gte: number } };
      data: { stock: { decrement: number } | { increment: number }; salesCount?: { increment: number } | { decrement: number } };
    }): Promise<{ count: number }>;
    findUnique(args: { where: { id: string }; select: { stock: true } }): Promise<{ stock: number } | null>;
  };
};

/**
 * Атомарно зменшує залишки. Умова `stock >= quantity` перевіряється в самому UPDATE,
 * тому два паралельні замовлення не можуть продати більше, ніж є на складі.
 * Якщо хоч одного товару не вистачає — кидає InsufficientStockError, і транзакція відкочується.
 */
export async function decrementStock(tx: StockTx, lines: StockLine[]): Promise<void> {
  // Однаковий порядок блокувань рядків запобігає взаємним блокуванням (deadlock)
  const sorted = [...lines].sort((a, b) => a.productId.localeCompare(b.productId));
  for (const line of sorted) {
    if (!Number.isInteger(line.quantity) || line.quantity <= 0) throw new Error("Некоректна кількість");
    const res = await tx.product.updateMany({
      where: { id: line.productId, isActive: true, stock: { gte: line.quantity } },
      data: { stock: { decrement: line.quantity }, salesCount: { increment: line.quantity } },
    });
    if (res.count !== 1) {
      const current = await tx.product.findUnique({ where: { id: line.productId }, select: { stock: true } });
      throw new InsufficientStockError(line.productId, line.name, Math.max(0, current?.stock ?? 0));
    }
  }
}

/** Повертає залишки (наприклад, при скасуванні замовлення). */
export async function restoreStock(tx: StockTx, lines: Array<{ productId: string | null; quantity: number }>): Promise<void> {
  const sorted = lines.filter((l): l is { productId: string; quantity: number } => !!l.productId)
    .sort((a, b) => a.productId.localeCompare(b.productId));
  for (const line of sorted) {
    await tx.product.updateMany({
      where: { id: line.productId },
      data: { stock: { increment: line.quantity }, salesCount: { decrement: line.quantity } },
    });
  }
}

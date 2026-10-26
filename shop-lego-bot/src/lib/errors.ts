/** Доменні помилки з повідомленням українською, яке можна показати користувачу. */
export class DomainError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
    this.name = "DomainError";
  }
}

export class NotFoundError extends DomainError {
  constructor(message: string) {
    super(message, "NOT_FOUND");
    this.name = "NotFoundError";
  }
}

export class InsufficientStockError extends DomainError {
  constructor(
    readonly productId: number,
    readonly requested: number,
    readonly available: number,
  ) {
    super(
      available > 0
        ? `Недостатньо товару на складі: доступно ${available}, запитано ${requested}`
        : "Товару немає в наявності",
      "INSUFFICIENT_STOCK",
    );
    this.name = "InsufficientStockError";
  }
}

export class InvalidTransitionError extends DomainError {
  constructor(message: string) {
    super(message, "INVALID_TRANSITION");
    this.name = "InvalidTransitionError";
  }
}

/** Порушення інваріантів складу — ознака помилки в даних; транзакція відкочується. */
export class InventoryInvariantError extends DomainError {
  constructor(message: string) {
    super(message, "INVENTORY_INVARIANT");
    this.name = "InventoryInvariantError";
  }
}

export class ValidationError extends DomainError {
  constructor(message: string) {
    super(message, "VALIDATION");
    this.name = "ValidationError";
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

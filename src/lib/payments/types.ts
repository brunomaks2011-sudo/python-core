// Загальний інтерфейс платіжного провайдера.
// Щоб додати Monobank чи WayForPay, реалізуйте PaymentProvider і зареєструйте його в ./index.ts.

export type PaymentOrder = {
  /** Номер замовлення в магазині */
  orderNumber: string;
  /** Унікальний ідентифікатор спроби оплати (передається провайдеру) */
  externalId: string;
  /** Сума в копійках */
  amount: number;
  currency: "UAH";
  description: string;
  /** Куди повернути покупця після оплати */
  resultUrl: string;
  /** URL для серверного callback (webhook) */
  serverUrl: string;
  language?: "uk" | "en";
};

export type PaymentRedirect = { url: string };

export type NormalizedPaymentStatus = "paid" | "pending" | "failed" | "refunded";

export type PaymentCallback = {
  externalId: string;
  status: NormalizedPaymentStatus;
  /** Сума в копійках, яку підтвердив провайдер */
  amount: number;
  currency: string;
  /** Сирий статус провайдера (для логів/адмінки) */
  providerStatus: string;
};

export interface PaymentProvider {
  readonly id: string;
  readonly title: string;
  isConfigured(): boolean;
  /** Формує платіж і повертає адресу сторінки оплати */
  createPayment(order: PaymentOrder): PaymentRedirect;
  /**
   * Перевіряє підпис і розбирає callback. Кидає InvalidSignatureError, якщо підпис невірний.
   * @param body поля форми/JSON запиту від провайдера
   */
  parseCallback(body: Record<string, string>): PaymentCallback;
  /** Опційно: активний запит статусу платежу (коли callback ще не дійшов) */
  checkStatus?(externalId: string): Promise<PaymentCallback | null>;
}

export class InvalidSignatureError extends Error {
  constructor() {
    super("Невірний підпис платіжного callback");
    this.name = "InvalidSignatureError";
  }
}

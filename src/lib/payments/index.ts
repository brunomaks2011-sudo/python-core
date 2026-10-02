import "server-only";
import { createLiqPayProvider } from "./liqpay";
import type { PaymentProvider } from "./types";

export * from "./types";

/** Реєстр платіжних провайдерів. Нові (Monobank, WayForPay) додаються тут. */
function buildProviders(): Record<string, PaymentProvider> {
  return {
    liqpay: createLiqPayProvider({
      publicKey: process.env.LIQPAY_PUBLIC_KEY ?? "",
      privateKey: process.env.LIQPAY_PRIVATE_KEY ?? "",
      // Sandbox за замовчуванням: бойовий режим лише при явному LIQPAY_SANDBOX=0
      sandbox: process.env.LIQPAY_SANDBOX !== "0",
    }),
  };
}

export function getPaymentProvider(id: string): PaymentProvider | null {
  return buildProviders()[id] ?? null;
}

/** Провайдер для онлайн-оплати за замовчуванням або null, якщо ключі не налаштовані. */
export function getOnlinePaymentProvider(): PaymentProvider | null {
  const p = getPaymentProvider("liqpay");
  return p?.isConfigured() ? p : null;
}

export function isSandbox(): boolean {
  return process.env.LIQPAY_SANDBOX !== "0";
}

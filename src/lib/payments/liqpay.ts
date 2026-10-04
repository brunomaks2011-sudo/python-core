import { createHash, timingSafeEqual } from "node:crypto";
import { kopecksToUahString, uahToKopecks } from "@/lib/money";
import {
  InvalidSignatureError,
  type NormalizedPaymentStatus,
  type PaymentCallback,
  type PaymentOrder,
  type PaymentProvider,
  type PaymentRedirect,
} from "./types";

// Документація LiqPay: https://www.liqpay.ua/doc/api/internet_acquiring/checkout
export const LIQPAY_CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout";
export const LIQPAY_API_URL = "https://www.liqpay.ua/api/request";

export type LiqPayConfig = { publicKey: string; privateKey: string; sandbox: boolean };

/** data = base64(JSON) */
export function encodeLiqPayData(params: Record<string, unknown>): string {
  return Buffer.from(JSON.stringify(params), "utf8").toString("base64");
}

export function decodeLiqPayData<T = Record<string, unknown>>(data: string): T {
  return JSON.parse(Buffer.from(data, "base64").toString("utf8")) as T;
}

/** signature = base64(sha1(private_key + data + private_key)) */
export function liqPaySignature(privateKey: string, data: string): string {
  return createHash("sha1").update(privateKey + data + privateKey).digest("base64");
}

/** Перевірка підпису з порівнянням за сталий час (захист від timing-атак). */
export function verifyLiqPaySignature(privateKey: string, data: string, signature: string): boolean {
  if (!privateKey || !data || !signature) return false;
  const expected = Buffer.from(liqPaySignature(privateKey, data));
  const given = Buffer.from(signature);
  return expected.length === given.length && timingSafeEqual(expected, given);
}

export function mapLiqPayStatus(status: string): NormalizedPaymentStatus {
  switch (status) {
    case "success":
    case "sandbox":
      return "paid";
    case "failure":
    case "error":
      return "failed";
    case "reversed":
    case "refund":
      return "refunded";
    default:
      // processing, wait_accept, 3ds_verify, prepared, ...
      return "pending";
  }
}

type LiqPayCallbackData = {
  public_key?: string;
  order_id: string;
  status: string;
  amount: number;
  currency: string;
  action?: string;
};

export function createLiqPayProvider(config: LiqPayConfig): PaymentProvider {
  return {
    id: "liqpay",
    title: "Карткою онлайн (LiqPay): Visa, Mastercard, Apple Pay, Google Pay",
    isConfigured: () => !!config.publicKey && !!config.privateKey,

    createPayment(order: PaymentOrder): PaymentRedirect {
      const params: Record<string, unknown> = {
        version: 3,
        public_key: config.publicKey,
        action: "pay",
        amount: kopecksToUahString(order.amount),
        currency: order.currency,
        description: order.description,
        order_id: order.externalId,
        result_url: order.resultUrl,
        server_url: order.serverUrl,
        language: order.language ?? "uk",
      };
      if (config.sandbox) params.sandbox = 1;
      const data = encodeLiqPayData(params);
      const signature = liqPaySignature(config.privateKey, data);
      const url = `${LIQPAY_CHECKOUT_URL}?${new URLSearchParams({ data, signature }).toString()}`;
      return { url };
    },

    parseCallback(body: Record<string, string>): PaymentCallback {
      const { data, signature } = body;
      if (!verifyLiqPaySignature(config.privateKey, data, signature)) throw new InvalidSignatureError();
      const payload = decodeLiqPayData<LiqPayCallbackData>(data);
      if (payload.public_key && payload.public_key !== config.publicKey) throw new InvalidSignatureError();
      return {
        externalId: String(payload.order_id),
        status: mapLiqPayStatus(payload.status),
        amount: uahToKopecks(Number(payload.amount)),
        currency: payload.currency,
        providerStatus: payload.status,
      };
    },

    async checkStatus(externalId: string): Promise<PaymentCallback | null> {
      const data = encodeLiqPayData({ version: 3, public_key: config.publicKey, action: "status", order_id: externalId });
      const signature = liqPaySignature(config.privateKey, data);
      try {
        const res = await fetch(LIQPAY_API_URL, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ data, signature }),
          signal: AbortSignal.timeout(8000),
          cache: "no-store",
        });
        const json = (await res.json()) as Partial<LiqPayCallbackData> & { result?: string };
        if (!json.status || !json.order_id) return null;
        return {
          externalId: String(json.order_id),
          status: mapLiqPayStatus(json.status),
          amount: uahToKopecks(Number(json.amount ?? 0)),
          currency: json.currency ?? "UAH",
          providerStatus: json.status,
        };
      } catch {
        return null;
      }
    },
  };
}

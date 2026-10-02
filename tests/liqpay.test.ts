import { describe, expect, it } from "vitest";
import {
  createLiqPayProvider,
  decodeLiqPayData,
  encodeLiqPayData,
  liqPaySignature,
  mapLiqPayStatus,
  verifyLiqPaySignature,
} from "@/lib/payments/liqpay";
import { InvalidSignatureError } from "@/lib/payments/types";

const PRIVATE = "sandbox_secret";
const PUBLIC = "sandbox_i000";

// Еталон обчислено незалежно: printf "$KEY$DATA$KEY" | openssl dgst -sha1 -binary | base64
const REF_DATA =
  "eyJ2ZXJzaW9uIjozLCJwdWJsaWNfa2V5Ijoic2FuZGJveF9pMDAwIiwiYWN0aW9uIjoicGF5IiwiYW1vdW50IjoiMTI5OS4wMCIsImN1cnJlbmN5IjoiVUFIIiwib3JkZXJfaWQiOiIyNjEwMDItMTIzNDUtYWJjIn0=";
const REF_SIGNATURE = "brUvHrx+hWHs9oXoc6nSLwvxCxQ=";

describe("підпис LiqPay", () => {
  it("кодує data так само, як LiqPay (base64 JSON)", () => {
    const data = encodeLiqPayData({
      version: 3, public_key: PUBLIC, action: "pay", amount: "1299.00", currency: "UAH", order_id: "261002-12345-abc",
    });
    expect(data).toBe(REF_DATA);
  });

  it("обчислює підпис base64(sha1(private + data + private))", () => {
    expect(liqPaySignature(PRIVATE, REF_DATA)).toBe(REF_SIGNATURE);
  });

  it("приймає правильний підпис", () => {
    expect(verifyLiqPaySignature(PRIVATE, REF_DATA, REF_SIGNATURE)).toBe(true);
  });

  it("відхиляє підроблений підпис, змінені дані або інший ключ", () => {
    expect(verifyLiqPaySignature(PRIVATE, REF_DATA, "AAAA" + REF_SIGNATURE.slice(4))).toBe(false);
    expect(verifyLiqPaySignature(PRIVATE, REF_DATA.replace("J2", "J3"), REF_SIGNATURE)).toBe(false);
    expect(verifyLiqPaySignature("other_key", REF_DATA, REF_SIGNATURE)).toBe(false);
    expect(verifyLiqPaySignature(PRIVATE, REF_DATA, "")).toBe(false);
    expect(verifyLiqPaySignature("", REF_DATA, REF_SIGNATURE)).toBe(false);
  });

  it("мапить статуси LiqPay", () => {
    expect(mapLiqPayStatus("success")).toBe("paid");
    expect(mapLiqPayStatus("sandbox")).toBe("paid");
    expect(mapLiqPayStatus("failure")).toBe("failed");
    expect(mapLiqPayStatus("error")).toBe("failed");
    expect(mapLiqPayStatus("reversed")).toBe("refunded");
    expect(mapLiqPayStatus("processing")).toBe("pending");
  });
});

describe("провайдер LiqPay", () => {
  const provider = createLiqPayProvider({ publicKey: PUBLIC, privateKey: PRIVATE, sandbox: true });

  it("формує підписане посилання на оплату в sandbox-режимі", () => {
    const { url } = provider.createPayment({
      orderNumber: "261002-12345",
      externalId: "261002-12345-abc",
      amount: 129900,
      currency: "UAH",
      description: "Тест",
      resultUrl: "https://shop.example/payment/return",
      serverUrl: "https://shop.example/api/payments/liqpay/callback",
    });
    const u = new URL(url);
    expect(u.origin + u.pathname).toBe("https://www.liqpay.ua/api/3/checkout");
    const data = u.searchParams.get("data")!;
    expect(verifyLiqPaySignature(PRIVATE, data, u.searchParams.get("signature")!)).toBe(true);
    const params = decodeLiqPayData<Record<string, unknown>>(data);
    expect(params).toMatchObject({ amount: "1299.00", currency: "UAH", sandbox: 1, order_id: "261002-12345-abc", public_key: PUBLIC });
  });

  it("розбирає callback з валідним підписом", () => {
    const data = encodeLiqPayData({ public_key: PUBLIC, order_id: "X-1", status: "success", amount: 1299, currency: "UAH" });
    const cb = provider.parseCallback({ data, signature: liqPaySignature(PRIVATE, data) });
    expect(cb).toEqual({ externalId: "X-1", status: "paid", amount: 129900, currency: "UAH", providerStatus: "success" });
  });

  it("кидає помилку для callback з невалідним підписом", () => {
    const data = encodeLiqPayData({ public_key: PUBLIC, order_id: "X-1", status: "success", amount: 1, currency: "UAH" });
    expect(() => provider.parseCallback({ data, signature: liqPaySignature("attacker", data) })).toThrow(InvalidSignatureError);
    expect(() => provider.parseCallback({ data } as Record<string, string>)).toThrow(InvalidSignatureError);
  });

  it("відхиляє callback, підписаний для іншого public_key", () => {
    const data = encodeLiqPayData({ public_key: "someone_else", order_id: "X-1", status: "success", amount: 1, currency: "UAH" });
    expect(() => provider.parseCallback({ data, signature: liqPaySignature(PRIVATE, data) })).toThrow(InvalidSignatureError);
  });
});

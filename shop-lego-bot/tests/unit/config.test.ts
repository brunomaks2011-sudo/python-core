import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { loadConfig } from "../../src/config/env.js";
import { ORDER_TRANSITIONS, canTransition } from "../../src/orders/orderStatus.js";

const base = {
  BOT_TOKEN: "123456789:AAEexampleexampleexampleexample",
  ADMIN_IDS: "111111111, 222222222",
  DATABASE_URL: "postgresql://u:p@localhost:5432/db",
};

describe("налаштування", () => {
  it("парсить мінімальний .env", () => {
    const c = loadConfig(base);
    assert.deepEqual(c.telegram.adminIds, [111111111n, 222222222n]);
    assert.equal(c.ai.enabled, false, "без ANTHROPIC_API_KEY ШІ вимкнено");
    assert.equal(c.ai.model, "claude-opus-5-5");
    assert.deepEqual(c.shop.paymentMethods, ["CASH_ON_DELIVERY", "CARD_TRANSFER"]);
    assert.equal(c.telegram.webhook, undefined);
  });
  it("вмикає ШІ за наявності ключа", () => {
    const c = loadConfig({ ...base, ANTHROPIC_API_KEY: "sk-ant-test" });
    assert.equal(c.ai.enabled, true);
  });
  it("відхиляє некоректні значення з українським поясненням", () => {
    assert.throws(() => loadConfig({ ...base, BOT_TOKEN: "abc" }), /BOT_TOKEN/);
    assert.throws(() => loadConfig({ ...base, ADMIN_IDS: "admin" }), /ADMIN_IDS/);
    assert.throws(() => loadConfig({ ...base, PAYMENT_METHODS: "BITCOIN" }), /спосіб оплати/);
    assert.throws(() => loadConfig({ BOT_TOKEN: base.BOT_TOKEN, ADMIN_IDS: base.ADMIN_IDS }), /DATABASE_URL/);
  });
});

describe("статуси замовлень", () => {
  it("скасування можливе лише до відправлення", () => {
    assert.equal(canTransition("CONFIRMED", "CANCELED"), true);
    assert.equal(canTransition("PACKING", "CANCELED"), true);
    assert.equal(canTransition("SHIPPED", "CANCELED"), false);
    assert.equal(canTransition("DELIVERED", "CANCELED"), false);
  });
  it("повернення лише після відправлення", () => {
    assert.equal(canTransition("SHIPPED", "RETURNED"), true);
    assert.equal(canTransition("DELIVERED", "RETURNED"), true);
    assert.equal(canTransition("CONFIRMED", "RETURNED"), false);
  });
  it("кінцеві статуси", () => {
    assert.deepEqual(ORDER_TRANSITIONS.CANCELED, []);
    assert.deepEqual(ORDER_TRANSITIONS.RETURNED, []);
  });
});

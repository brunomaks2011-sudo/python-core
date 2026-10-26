import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { parse } from "dotenv";
import { loadConfig } from "../../src/config/env.js";

describe(".env.example", () => {
  const env = parse(readFileSync(new URL("../../.env.example", import.meta.url), "utf8"));

  it("після заповнення BOT_TOKEN дає коректні налаштування", () => {
    const config = loadConfig({ ...env, BOT_TOKEN: "123456789:AAexampleexampleexampleexample" });
    assert.equal(config.ai.enabled, false, "без ключа ШІ вимкнено");
    assert.deepEqual(config.shop.paymentMethods, ["CASH_ON_DELIVERY", "CARD_TRANSFER"]);
    assert.match(config.shop.paymentDetails, /\nОтримувач/, "\\n у .env стає переносом рядка");
    assert.equal(config.healthPort, 8080);
    assert.equal(config.telegram.webhook, undefined, "за замовчуванням — long polling");
    assert.equal(config.telegram.apiRoot, undefined);
  });

  it("порожні необов'язкові значення не ламають запуск", () => {
    const config = loadConfig({ ...env, BOT_TOKEN: "123456789:AAexampleexampleexampleexample", HEALTH_PORT: "" });
    assert.equal(config.healthPort, undefined);
  });

  it("без BOT_TOKEN запуск зупиняється зрозумілою помилкою", () => {
    assert.throws(() => loadConfig(env), /BOT_TOKEN/);
  });
});

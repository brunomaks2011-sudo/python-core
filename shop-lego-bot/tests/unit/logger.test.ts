import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { TelegramError } from "telegraf";
import { maskPhone, serializeError } from "../../src/lib/logger.js";

describe("журнал не містить персональних даних", () => {
  it("з помилки Telegram прибирається тіло запиту", () => {
    const err = new TelegramError(
      { error_code: 400, description: "Bad Request: chat not found" },
      { method: "sendMessage", payload: { chat_id: 1, text: "Олена Коваль, +380501112233, Львів" } },
    );
    const json = JSON.stringify(serializeError(err));
    assert.doesNotMatch(json, /380501112233|Олена/);
    assert.match(json, /sendMessage/);
    assert.match(json, /chat not found/);
  });

  it("маскування телефону", () => {
    assert.equal(maskPhone("+380501112233"), "+380***33");
    assert.equal(maskPhone(null), "—");
  });
});

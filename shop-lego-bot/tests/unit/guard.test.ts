import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { NumberWhitelist, findUnverifiedNumbers } from "../../src/ai/guard.js";

describe("перевірка чисел у відповіді ШІ", () => {
  const toolResult = JSON.stringify({
    products: [{ id: 3, set_number: "42151", price_uah: 1800, available_qty: 5, pieces: 905, age_min: 9 }],
  });

  it("пропускає числа з результатів інструментів", () => {
    const wl = new NumberWhitelist();
    wl.addText(toolResult);
    assert.deepEqual(findUnverifiedNumbers("Так, LEGO Technic 42151 є! Ціна: 1 800 грн, 905 деталей.", wl), []);
  });

  it("ловить вигадану ціну й кількість деталей", () => {
    const wl = new NumberWhitelist();
    wl.addText(toolResult);
    assert.deepEqual(findUnverifiedNumbers("Ціна 1500 грн, у наборі 1254 деталі.", wl), ["1500", "1254"]);
  });

  it("дозволяє дрібні числа (кількість, нумерація)", () => {
    const wl = new NumberWhitelist();
    assert.deepEqual(findUnverifiedNumbers("Можу показати 3 варіанти, оберіть 1 або 2.", wl), []);
  });

  it("ловить вигаданий номер набору", () => {
    const wl = new NumberWhitelist();
    wl.addText(toolResult);
    assert.deepEqual(findUnverifiedNumbers("Також раджу 42115.", wl), ["42115"]);
  });

  it("дозволяє числа з повідомлення покупця", () => {
    const wl = new NumberWhitelist();
    wl.addText("Що є до 2000 грн?");
    assert.deepEqual(findUnverifiedNumbers("Ось набори до 2000 грн:", wl), []);
  });
});

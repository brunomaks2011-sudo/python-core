import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parseMessage, type Intent } from "../../src/ai/intentParser.js";
import { detectTheme } from "../../src/catalog/themes.js";

const intent = (text: string, hasLastShown = false): Intent => parseMessage(text, { hasLastShown }).intent;

function searchFilters(text: string) {
  const i = intent(text);
  assert.equal(i.type, "search", `«${text}» → ${JSON.stringify(i)}`);
  return (i as Extract<Intent, { type: "search" }>).filters;
}

describe("резервний розбір (приклади з технічного завдання)", () => {
  it("«Чи є LEGO Technic?»", () => {
    assert.equal(searchFilters("Чи є LEGO Technic?").theme, "LEGO Technic");
  });
  it("«Покажи набори LEGO до 2000 грн»", () => {
    const f = searchFilters("Покажи набори LEGO до 2000 грн");
    assert.equal(f.maxPrice, 2000);
    assert.equal(f.theme, null);
    assert.equal(f.text, null);
  });
  it("«Є LEGO Star Wars?»", () => {
    assert.equal(searchFilters("Є LEGO Star Wars?").theme, "LEGO Star Wars");
  });
  it("«Шукаю набір LEGO 42151»", () => {
    assert.deepEqual(intent("Шукаю набір LEGO 42151"), { type: "product_lookup", setNumbers: ["42151"] });
  });
  it("«Які набори є для дітей від 8 років?»", () => {
    const f = searchFilters("Які набори є для дітей від 8 років?");
    assert.equal(f.childAge, 8);
    assert.equal(f.maxPrice, null);
    assert.equal(f.text, null);
  });
  it("«Чи є цей набір у наявності?» з показаним раніше товаром", () => {
    assert.deepEqual(intent("Чи є цей набір у наявності?", true), { type: "about_last_shown", aspect: "availability" });
  });
  it("«Що можна купити за 1500 грн?»", () => {
    const f = searchFilters("Що можна купити за 1500 грн?");
    assert.equal(f.maxPrice, 1500);
    assert.equal(f.text, null);
  });
});

describe("розмовні повідомлення", () => {
  it("«Є технік?»", () => {
    assert.equal(searchFilters("Є технік?").theme, "LEGO Technic");
  });
  it("«Покажи зоряні війни»", () => {
    assert.equal(searchFilters("Покажи зоряні війни").theme, "LEGO Star Wars");
  });
  it("«Скільки коштує цей лего?»", () => {
    assert.deepEqual(intent("Скільки коштує цей лего?", true), { type: "about_last_shown", aspect: "price" });
  });
  it("«Що є до двох тисяч?»", () => {
    assert.equal(searchFilters("Що є до двох тисяч?").maxPrice, 2000);
  });
  it("«Хочу замовити два набори»", () => {
    assert.deepEqual(intent("Хочу замовити два набори"), { type: "order", setNumber: null, quantity: 2 });
  });
  it("«Хочу замовити 42151»", () => {
    assert.deepEqual(intent("Хочу замовити 42151"), { type: "order", setNumber: "42151", quantity: null });
  });
  it("«Я вже у вас купував»", () => {
    assert.deepEqual(intent("Я вже у вас купував"), { type: "my_orders" });
  });
  it("привітання з запитом", () => {
    const parsed = parseMessage("Привіт! Є LEGO Technic?", { hasLastShown: false });
    assert.equal(parsed.greeting, true);
    assert.equal(parsed.intent.type, "search");
  });
  it("лише привітання", () => {
    assert.deepEqual(parseMessage("Добрий день!", { hasLastShown: false }), {
      greeting: true,
      intent: { type: "greeting_only" },
    });
  });
  it("доставка й оплата", () => {
    assert.deepEqual(intent("Як у вас з доставкою?"), { type: "shop_info", topic: "delivery" });
    assert.deepEqual(intent("Можна оплатити карткою?"), { type: "shop_info", topic: "payment" });
  });
  it("вживані набори", () => {
    assert.equal(searchFilters("є вживані набори?").condition, "USED");
  });
  it("текстовий пошук із транслітерацією", () => {
    assert.equal(searchFilters("шукаю бугатті").text, "бугатті");
  });
});

describe("розпізнавання тематик", () => {
  it("варіанти написання", () => {
    assert.equal(detectTheme("гаррі поттера")?.name, "LEGO Harry Potter");
    assert.equal(detectTheme("ніндзяго")?.name, "LEGO Ninjago");
    assert.equal(detectTheme("техніку")?.name, "LEGO Technic");
    assert.equal(detectTheme("сіті")?.name, "LEGO City");
    assert.equal(detectTheme("просто набір")?.name, undefined);
  });
});

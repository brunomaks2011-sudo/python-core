import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  extractSetNumbers,
  looksLikeQuestion,
  parseChildAge,
  parsePriceRange,
  parseQuantity,
  replaceNumberWords,
  transliterationVariants,
} from "../../src/lib/text.js";

describe("replaceNumberWords", () => {
  it("перетворює числа словами", () => {
    assert.equal(replaceNumberWords("до двох тисяч"), "до 2000");
    assert.equal(replaceNumberWords("Хочу замовити два набори"), "хочу замовити 2 набори");
    assert.equal(replaceNumberWords("півтори тисячі"), "1500");
    assert.equal(replaceNumberWords("до 2к"), "до 2000");
    assert.equal(replaceNumberWords("до 2,5 тис"), "до 2500");
    assert.equal(replaceNumberWords("дві тисячі п'ятсот"), "2500");
    assert.equal(replaceNumberWords("1 800 грн"), "1800 грн");
  });
});

describe("parsePriceRange", () => {
  it("розпізнає верхню межу", () => {
    assert.deepEqual(parsePriceRange("Покажи набори LEGO до 2000 грн"), { max: 2000 });
    assert.deepEqual(parsePriceRange("Що є до двох тисяч?"), { max: 2000 });
    assert.deepEqual(parsePriceRange("Що можна купити за 1500 грн?"), { max: 1500 });
    assert.deepEqual(parsePriceRange("щось дешевше 1000"), { max: 1000 });
  });
  it("розпізнає діапазон", () => {
    assert.deepEqual(parsePriceRange("від 1000 до 3000 грн"), { min: 1000, max: 3000 });
    assert.deepEqual(parsePriceRange("1000-2000 грн"), { min: 1000, max: 2000 });
  });
  it("не плутає вік і номер набору з ціною", () => {
    assert.equal(parsePriceRange("для дітей від 8 років"), null);
    assert.equal(parsePriceRange("від 10 років"), null);
    assert.equal(parsePriceRange("Шукаю набір LEGO 42151"), null);
  });
});

describe("parseChildAge", () => {
  it("розпізнає вік", () => {
    assert.equal(parseChildAge("Які набори є для дітей від 8 років?"), 8);
    assert.equal(parseChildAge("для сина 10 років"), 10);
    assert.equal(parseChildAge("набори 12+"), 12);
    assert.equal(parseChildAge("для семирічного хлопчика"), 7);
    assert.equal(parseChildAge("Покажи набори до 2000 грн"), null);
  });
});

describe("extractSetNumbers", () => {
  it("знаходить номер набору", () => {
    assert.deepEqual(extractSetNumbers("Шукаю набір LEGO 42151"), ["42151"]);
    assert.deepEqual(extractSetNumbers("Чи є LEGO 42151?"), ["42151"]);
    assert.deepEqual(extractSetNumbers("Є 75192-1 та 42115."), ["75192", "42115"]);
  });
  it("не вважає ціни та вік номерами наборів", () => {
    assert.deepEqual(extractSetNumbers("до 2000 грн"), []);
    assert.deepEqual(extractSetNumbers("до 2000"), []);
    assert.deepEqual(extractSetNumbers("за 1500"), []);
    assert.deepEqual(extractSetNumbers("набори 1 800 грн"), []);
  });
});

describe("parseQuantity", () => {
  it("розпізнає кількість", () => {
    assert.equal(parseQuantity("2"), 2);
    assert.equal(parseQuantity("два"), 2);
    assert.equal(parseQuantity("дві штуки"), 2);
    assert.equal(parseQuantity("3 шт"), 3);
    assert.equal(parseQuantity("не знаю"), null);
    assert.equal(parseQuantity("0"), null);
  });
});

describe("looksLikeQuestion", () => {
  it("відрізняє питання від відповіді на крок оформлення", () => {
    assert.equal(looksLikeQuestion("а є ще технік?"), true);
    assert.equal(looksLikeQuestion("Покажи зоряні війни"), true);
    assert.equal(looksLikeQuestion("Іван Петренко"), false);
    assert.equal(looksLikeQuestion("Київ"), false);
    assert.equal(looksLikeQuestion("Чигирин"), false);
  });
});

describe("transliterationVariants", () => {
  it("дає латинські варіанти", () => {
    assert.ok(transliterationVariants("бугатті").includes("bugatti"));
    assert.deepEqual(transliterationVariants("Bugatti"), []);
  });
});

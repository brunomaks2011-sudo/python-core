import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  normalizePhone,
  parsePrice,
  parseSignedInt,
  validateCity,
  validateDeliveryPoint,
  validateFullName,
  validateSetNumber,
} from "../../src/lib/validation.js";

const value = <T>(r: { ok: true; value: T } | { ok: false; error: string }) => (r.ok ? r.value : null);

describe("normalizePhone", () => {
  it("нормалізує українські номери", () => {
    assert.equal(value(normalizePhone("+380 67 123 45 67")), "+380671234567");
    assert.equal(value(normalizePhone("067-123-45-67")), "+380671234567");
    assert.equal(value(normalizePhone("(067) 123 4567")), "+380671234567");
    assert.equal(value(normalizePhone("380671234567")), "+380671234567");
  });
  it("приймає міжнародні номери з +", () => {
    assert.equal(value(normalizePhone("+48 512 345 678")), "+48512345678");
  });
  it("відхиляє некоректні", () => {
    assert.equal(normalizePhone("привіт").ok, false);
    assert.equal(normalizePhone("12345").ok, false);
    assert.equal(normalizePhone("+380 67 123").ok, false);
  });
});

describe("validateFullName", () => {
  it("приймає ім’я та прізвище", () => {
    assert.equal(value(validateFullName("іван петренко")), "Іван Петренко");
    assert.equal(value(validateFullName("Олександра Коваль-Мельник")), "Олександра Коваль-Мельник");
    assert.equal(value(validateFullName("Д’Артаньян Гасконський")), "Д'Артаньян Гасконський");
  });
  it("вимагає прізвище й відхиляє цифри", () => {
    assert.equal(validateFullName("Іван").ok, false);
    assert.equal(validateFullName("Іван 123").ok, false);
  });
});

describe("місто та відділення", () => {
  it("валідує місто", () => {
    assert.equal(value(validateCity("кам'янець-подільський")), "Кам'янець-подільський");
    assert.equal(validateCity("123").ok, false);
  });
  it("номер відділення перетворюється на зрозумілий текст", () => {
    assert.equal(value(validateDeliveryPoint("12")), "Відділення №12");
    assert.equal(value(validateDeliveryPoint("Поштомат 3045")), "Поштомат 3045");
  });
});

describe("ціни та числа", () => {
  it("parsePrice", () => {
    assert.equal(value(parsePrice("1800")), "1800.00");
    assert.equal(value(parsePrice("1 799,50 грн")), "1799.50");
    assert.equal(parsePrice("0").ok, false);
    assert.equal(parsePrice("дорого").ok, false);
  });
  it("parseSignedInt", () => {
    assert.equal(value(parseSignedInt("+3")), 3);
    assert.equal(value(parseSignedInt("-2")), -2);
    assert.equal(parseSignedInt("0").ok, false);
  });
  it("validateSetNumber", () => {
    assert.equal(value(validateSetNumber("75192-1")), "75192");
    assert.equal(value(validateSetNumber("#42151")), "42151");
    assert.equal(validateSetNumber("42 151").ok, false);
  });
});

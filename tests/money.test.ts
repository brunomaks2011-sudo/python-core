import { describe, expect, it } from "vitest";
import { discountPercent, kopecksToUahString, uahToKopecks } from "@/lib/money";
import { pluralUk, slugify } from "@/lib/utils";

describe("гроші", () => {
  it("конвертує гривні в копійки без похибок float", () => {
    expect(uahToKopecks(19.99)).toBe(1999);
    expect(uahToKopecks(0.1 + 0.2)).toBe(30);
  });
  it("форматує суму для LiqPay", () => {
    expect(kopecksToUahString(129900)).toBe("1299.00");
    expect(kopecksToUahString(5)).toBe("0.05");
  });
  it("рахує відсоток знижки", () => {
    expect(discountPercent(8000, 10000)).toBe(20);
    expect(discountPercent(10000, 8000)).toBeNull();
    expect(discountPercent(10000, null)).toBeNull();
  });
});

describe("утиліти", () => {
  it("транслітерує slug", () => {
    expect(slugify("Пожежна станція 60401")).toBe("pozhezhna-stantsiia-60401");
  });
  it("відмінює слова", () => {
    expect(pluralUk(1, ["товар", "товари", "товарів"])).toBe("товар");
    expect(pluralUk(3, ["товар", "товари", "товарів"])).toBe("товари");
    expect(pluralUk(11, ["товар", "товари", "товарів"])).toBe("товарів");
  });
});

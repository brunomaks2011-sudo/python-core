import { describe, expect, it, vi } from "vitest";
import { quoteDelivery } from "@/lib/delivery/quote";
import type { ShopSettings } from "@/lib/settings";

const settings: ShopSettings = {
  freeShippingThreshold: 200000,
  ukrposhtaRate: 6000,
  npWarehouseFallbackRate: 8000,
  npCourierFallbackRate: 12000,
};
const base = { itemsTotal: 100000, weightGrams: 1500, cityRef: "db5c88f0-391c-11dd-90d9-001a92567626" };

describe("розрахунок доставки", () => {
  it("самовивіз безкоштовний", async () => {
    expect((await quoteDelivery({ ...base, method: "PICKUP" }, settings, null)).cost).toBe(0);
  });

  it("Укрпошта — фіксований тариф з налаштувань", async () => {
    const q = await quoteDelivery({ ...base, method: "UKRPOSHTA" }, settings, null);
    expect(q).toMatchObject({ cost: 6000, source: "flat" });
  });

  it("без ключа Нової Пошти — резервний тариф", async () => {
    expect(await quoteDelivery({ ...base, method: "NP_WAREHOUSE" }, settings, null)).toMatchObject({ cost: 8000, source: "fallback" });
    expect(await quoteDelivery({ ...base, method: "NP_COURIER" }, settings, null)).toMatchObject({ cost: 12000, source: "fallback" });
  });

  it("з API — передає вагу, оголошену вартість і тип послуги", async () => {
    const np = vi.fn().mockResolvedValue(9500);
    const q = await quoteDelivery({ ...base, method: "NP_COURIER" }, settings, np);
    expect(q).toMatchObject({ cost: 9500, source: "api" });
    expect(np).toHaveBeenCalledWith({ recipientCityRef: base.cityRef, weightKg: 1.5, declaredValueUah: 1000, serviceType: "WarehouseDoors" });
  });

  it("якщо API впало — резервний тариф, сайт працює", async () => {
    const np = vi.fn().mockRejectedValue(new Error("timeout"));
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(await quoteDelivery({ ...base, method: "NP_WAREHOUSE" }, settings, np)).toMatchObject({ cost: 8000, source: "fallback" });
  });

  it("безкоштовна доставка від порогу", async () => {
    const q = await quoteDelivery({ ...base, itemsTotal: 250000, method: "UKRPOSHTA" }, settings, null);
    expect(q).toMatchObject({ cost: 0, baseCost: 6000, free: true });
  });
});

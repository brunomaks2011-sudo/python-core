import type { DeliveryMethod } from "@prisma/client";
import { applyFreeShipping } from "@/lib/cart/calc";
import type { ShopSettings } from "@/lib/settings";

export type DeliveryQuote = {
  method: DeliveryMethod;
  /** Вартість до застосування безкоштовної доставки, копійки */
  baseCost: number;
  /** Підсумкова вартість для покупця, копійки */
  cost: number;
  free: boolean;
  /** api — розраховано Новою Поштою; fallback — резервний тариф; flat — фіксований тариф */
  source: "api" | "fallback" | "flat";
  note?: string;
};

export type NpPriceFn = (p: {
  recipientCityRef: string;
  weightKg: number;
  declaredValueUah: number;
  serviceType: "WarehouseWarehouse" | "WarehouseDoors" | "WarehousePostomat";
}) => Promise<number>;

/**
 * Розрахунок вартості доставки. Функція ціни Нової Пошти передається ззовні,
 * тож модуль тестується без мережі. Якщо API недоступне — береться резервний тариф.
 */
export async function quoteDelivery(
  input: { method: DeliveryMethod; cityRef?: string | null; itemsTotal: number; weightGrams: number },
  settings: ShopSettings,
  npPrice: NpPriceFn | null,
): Promise<DeliveryQuote> {
  const { method, itemsTotal } = input;
  const finish = (baseCost: number, source: DeliveryQuote["source"], note?: string): DeliveryQuote => {
    const { cost, free } = applyFreeShipping(itemsTotal, baseCost, settings.freeShippingThreshold);
    return { method, baseCost, cost, free, source, note };
  };

  switch (method) {
    case "PICKUP":
      return { method, baseCost: 0, cost: 0, free: true, source: "flat" };
    case "UKRPOSHTA":
      return finish(settings.ukrposhtaRate, "flat");
    case "NP_WAREHOUSE":
    case "NP_POSTOMAT":
    case "NP_COURIER": {
      const fallback = method === "NP_COURIER" ? settings.npCourierFallbackRate : settings.npWarehouseFallbackRate;
      if (!npPrice || !input.cityRef) {
        return finish(fallback, "fallback", npPrice ? "Оберіть місто для точного розрахунку" : undefined);
      }
      try {
        const price = await npPrice({
          recipientCityRef: input.cityRef,
          weightKg: Math.max(0.1, input.weightGrams / 1000),
          declaredValueUah: itemsTotal / 100,
          serviceType: method === "NP_COURIER" ? "WarehouseDoors" : method === "NP_POSTOMAT" ? "WarehousePostomat" : "WarehouseWarehouse",
        });
        return finish(price, "api");
      } catch (e) {
        console.warn("[delivery] Nova Poshta price failed, using fallback:", (e as Error).message);
        return finish(fallback, "fallback", "Орієнтовна вартість (сервіс Нової Пошти недоступний)");
      }
    }
  }
}

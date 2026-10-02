import { prisma } from "@/lib/prisma";
import { uahToKopecks } from "@/lib/money";

export type ShopSettings = {
  freeShippingThreshold: number;
  ukrposhtaRate: number;
  npWarehouseFallbackRate: number;
  npCourierFallbackRate: number;
};

function envUah(name: string, fallback: number): number {
  const raw = process.env[name];
  const n = raw ? Number(raw) : NaN;
  return uahToKopecks(Number.isFinite(n) && n >= 0 ? n : fallback);
}

/** Значення за замовчуванням з .env (у копійках). */
export function defaultSettings(): ShopSettings {
  return {
    freeShippingThreshold: envUah("FREE_SHIPPING_THRESHOLD_UAH", 2000),
    ukrposhtaRate: envUah("UKRPOSHTA_RATE_UAH", 60),
    npWarehouseFallbackRate: envUah("NP_FALLBACK_WAREHOUSE_RATE_UAH", 80),
    npCourierFallbackRate: envUah("NP_FALLBACK_COURIER_RATE_UAH", 120),
  };
}

/** Налаштування з БД (адмінка) з підстановкою значень з .env. */
export async function getShopSettings(): Promise<ShopSettings> {
  const row = await prisma.storeSettings.findUnique({ where: { id: 1 } }).catch(() => null);
  if (!row) return defaultSettings();
  return {
    freeShippingThreshold: row.freeShippingThreshold,
    ukrposhtaRate: row.ukrposhtaRate,
    npWarehouseFallbackRate: row.npWarehouseFallbackRate,
    npCourierFallbackRate: row.npCourierFallbackRate,
  };
}

export function pickupAddress(): string {
  return process.env.PICKUP_ADDRESS || "м. Київ (адресу уточнить менеджер)";
}

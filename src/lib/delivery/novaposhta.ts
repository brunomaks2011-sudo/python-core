import "server-only";

// Клієнт офіційного API Нової Пошти (JSON API 2.0).
// Документація: https://developers.novaposhta.ua/

const NP_API_URL = "https://api.novaposhta.ua/v2.0/json/";
const TIMEOUT_MS = 6000;

export type NpCity = { ref: string; name: string; area: string };
export type NpWarehouse = { ref: string; name: string; number: string; category: "Branch" | "Postomat" | string };

export function isNovaPoshtaConfigured(): boolean {
  return !!process.env.NOVA_POSHTA_API_KEY;
}

type NpResponse<T> = { success: boolean; data: T[]; errors: string[] };

async function npRequest<T>(modelName: string, calledMethod: string, methodProperties: Record<string, unknown>): Promise<T[]> {
  const apiKey = process.env.NOVA_POSHTA_API_KEY;
  if (!apiKey) throw new Error("NOVA_POSHTA_API_KEY не задано");
  const res = await fetch(NP_API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ apiKey, modelName, calledMethod, methodProperties }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Nova Poshta API HTTP ${res.status}`);
  const json = (await res.json()) as NpResponse<T>;
  if (!json.success) throw new Error(`Nova Poshta API: ${json.errors?.join("; ") || "невідома помилка"}`);
  return json.data;
}

// Простий in-memory кеш, щоб не навантажувати API однаковими запитами
const cache = new Map<string, { at: number; value: unknown }>();
async function cached<T>(key: string, ttlMs: number, fn: () => Promise<T>): Promise<T> {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < ttlMs) return hit.value as T;
  const value = await fn();
  cache.set(key, { at: Date.now(), value });
  if (cache.size > 2000) cache.delete(cache.keys().next().value!);
  return value;
}

export async function searchCities(query: string): Promise<NpCity[]> {
  const q = query.trim();
  if (q.length < 2) return [];
  return cached(`cities:${q.toLowerCase()}`, 6 * 3600_000, async () => {
    const data = await npRequest<{ Ref: string; Description: string; AreaDescription: string; SettlementTypeDescription: string }>(
      "Address",
      "getCities",
      { FindByString: q, Limit: "20", Page: "1" },
    );
    return data.map((c) => ({ ref: c.Ref, name: c.Description, area: c.AreaDescription }));
  });
}

export async function getWarehouses(cityRef: string, kind: "warehouse" | "postomat", query = ""): Promise<NpWarehouse[]> {
  const all = await cached(`wh:${cityRef}`, 6 * 3600_000, async () => {
    const data = await npRequest<{ Ref: string; Description: string; Number: string; CategoryOfWarehouse: string }>(
      "Address",
      "getWarehouses",
      { CityRef: cityRef, Limit: "1000", Page: "1" },
    );
    return data.map((w) => ({ ref: w.Ref, name: w.Description, number: w.Number, category: w.CategoryOfWarehouse }));
  });
  const q = query.trim().toLowerCase();
  return all
    .filter((w) => (kind === "postomat" ? w.category === "Postomat" : w.category !== "Postomat"))
    .filter((w) => !q || w.name.toLowerCase().includes(q) || w.number === q)
    .slice(0, 50);
}

/**
 * Розрахунок вартості доставки через InternetDocument.getDocumentPrice.
 * @returns вартість у копійках
 */
export async function getDeliveryPrice(params: {
  recipientCityRef: string;
  weightKg: number;
  declaredValueUah: number;
  serviceType: "WarehouseWarehouse" | "WarehouseDoors" | "WarehousePostomat";
}): Promise<number> {
  const sender = process.env.NOVA_POSHTA_SENDER_CITY_REF || "8d5a980d-391c-11dd-90d9-001a92567626";
  const weight = Math.max(0.1, Math.round(params.weightKg * 10) / 10);
  const key = `price:${params.recipientCityRef}:${weight}:${Math.round(params.declaredValueUah)}:${params.serviceType}`;
  return cached(key, 3600_000, async () => {
    const data = await npRequest<{ Cost: number | string }>("InternetDocument", "getDocumentPrice", {
      CitySender: sender,
      CityRecipient: params.recipientCityRef,
      Weight: String(weight),
      ServiceType: params.serviceType === "WarehousePostomat" ? "WarehouseWarehouse" : params.serviceType,
      Cost: String(Math.max(1, Math.round(params.declaredValueUah))),
      CargoType: "Parcel",
      SeatsAmount: "1",
    });
    const cost = Number(data[0]?.Cost);
    if (!Number.isFinite(cost) || cost < 0) throw new Error("Nova Poshta API: некоректна вартість");
    return Math.round(cost * 100);
  });
}

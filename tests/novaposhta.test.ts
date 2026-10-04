import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getDeliveryPrice, getWarehouses, isNovaPoshtaConfigured, searchCities } from "@/lib/delivery/novaposhta";

const KYIV = "8d5a980d-391c-11dd-90d9-001a92567626";
const LVIV = "db5c88f0-391c-11dd-90d9-001a92567626";

function mockApi(data: unknown[], success = true) {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ success, data, errors: success ? [] : ["API key expired"] }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}
const body = (fn: ReturnType<typeof vi.fn>) => JSON.parse(fn.mock.calls[0][1].body);

describe("клієнт API Нової Пошти", () => {
  beforeEach(() => vi.stubEnv("NOVA_POSHTA_API_KEY", "test-key"));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("налаштований лише з ключем", () => {
    expect(isNovaPoshtaConfigured()).toBe(true);
    vi.stubEnv("NOVA_POSHTA_API_KEY", "");
    expect(isNovaPoshtaConfigured()).toBe(false);
  });

  it("шукає міста через Address.getCities", async () => {
    const fn = mockApi([{ Ref: LVIV, Description: "Львів", AreaDescription: "Львівська", SettlementTypeDescription: "місто" }]);
    expect(await searchCities("Льві")).toEqual([{ ref: LVIV, name: "Львів", area: "Львівська" }]);
    expect(body(fn)).toMatchObject({ apiKey: "test-key", modelName: "Address", calledMethod: "getCities", methodProperties: { FindByString: "Льві" } });
  });

  it("не робить запит для коротких рядків", async () => {
    const fn = mockApi([]);
    expect(await searchCities("Л")).toEqual([]);
    expect(fn).not.toHaveBeenCalled();
  });

  it("розділяє відділення і поштомати", async () => {
    mockApi([
      { Ref: "w1", Description: "Відділення №1: вул. Городоцька, 1", Number: "1", CategoryOfWarehouse: "Branch" },
      { Ref: "p1", Description: "Поштомат №5001", Number: "5001", CategoryOfWarehouse: "Postomat" },
      { Ref: "w2", Description: "Відділення №2: вул. Шевченка, 5", Number: "2", CategoryOfWarehouse: "Branch" },
    ]);
    expect((await getWarehouses(LVIV, "postomat")).map((w) => w.ref)).toEqual(["p1"]);
    expect((await getWarehouses(LVIV, "warehouse")).map((w) => w.ref)).toEqual(["w1", "w2"]);
    expect((await getWarehouses(LVIV, "warehouse", "шевч")).map((w) => w.ref)).toEqual(["w2"]);
    expect((await getWarehouses(LVIV, "warehouse", "1")).map((w) => w.ref)).toEqual(["w1"]);
  });

  it("рахує вартість через InternetDocument.getDocumentPrice і повертає копійки", async () => {
    const fn = mockApi([{ Cost: 95 }]);
    const cost = await getDeliveryPrice({ recipientCityRef: LVIV, weightKg: 1.234, declaredValueUah: 1499, serviceType: "WarehouseDoors" });
    expect(cost).toBe(9500);
    expect(body(fn)).toMatchObject({
      modelName: "InternetDocument",
      calledMethod: "getDocumentPrice",
      methodProperties: { CitySender: KYIV, CityRecipient: LVIV, Weight: "1.2", ServiceType: "WarehouseDoors", Cost: "1499", CargoType: "Parcel" },
    });
  });

  it("поштомат рахується як відділення", async () => {
    const fn = mockApi([{ Cost: "70" }]);
    await getDeliveryPrice({ recipientCityRef: LVIV, weightKg: 0.5, declaredValueUah: 500, serviceType: "WarehousePostomat" });
    expect(body(fn).methodProperties.ServiceType).toBe("WarehouseWarehouse");
  });

  it("кидає помилку, якщо API повернуло success: false (далі спрацює резервний тариф)", async () => {
    mockApi([], false);
    await expect(getDeliveryPrice({ recipientCityRef: LVIV, weightKg: 9, declaredValueUah: 1, serviceType: "WarehouseWarehouse" })).rejects.toThrow(
      /API key expired/,
    );
  });
});

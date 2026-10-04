import "server-only";
import type { DeliveryMethod } from "@prisma/client";
import { getShopSettings } from "@/lib/settings";
import { getDeliveryPrice, isNovaPoshtaConfigured } from "./novaposhta";
import { quoteDelivery } from "./quote";

/** Серверний розрахунок вартості доставки з поточними налаштуваннями магазину. */
export async function getDeliveryQuote(input: { method: DeliveryMethod; cityRef?: string | null; itemsTotal: number; weightGrams: number }) {
  const settings = await getShopSettings();
  return quoteDelivery(input, settings, isNovaPoshtaConfigured() ? getDeliveryPrice : null);
}

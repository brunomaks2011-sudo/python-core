import type { DeliveryMethod } from "@prisma/client";

export const DELIVERY_METHODS: Record<DeliveryMethod, { label: string; short: string; carrier: "np" | "ukrposhta" | "pickup" }> = {
  NP_WAREHOUSE: { label: "Нова Пошта — відділення", short: "НП відділення", carrier: "np" },
  NP_POSTOMAT: { label: "Нова Пошта — поштомат", short: "НП поштомат", carrier: "np" },
  NP_COURIER: { label: "Нова Пошта — кур'єр за адресою", short: "НП кур'єр", carrier: "np" },
  UKRPOSHTA: { label: "Укрпошта — до відділення", short: "Укрпошта", carrier: "ukrposhta" },
  PICKUP: { label: "Самовивіз з магазину", short: "Самовивіз", carrier: "pickup" },
};

export const DELIVERY_METHOD_KEYS = Object.keys(DELIVERY_METHODS) as DeliveryMethod[];

/** Людиночитний опис адреси доставки з JSON-поля замовлення. */
export function describeDelivery(method: DeliveryMethod, data: unknown): string {
  const d = (data ?? {}) as Record<string, string | undefined>;
  switch (method) {
    case "NP_WAREHOUSE":
    case "NP_POSTOMAT":
      return [d.city, d.warehouse].filter(Boolean).join(", ");
    case "NP_COURIER":
      return [d.city, d.street && `${d.street} ${d.building ?? ""}`.trim(), d.apartment && `кв. ${d.apartment}`]
        .filter(Boolean)
        .join(", ");
    case "UKRPOSHTA":
      return [d.postalCode, d.city, d.street && `${d.street} ${d.building ?? ""}`.trim()].filter(Boolean).join(", ");
    case "PICKUP":
      return d.address ?? "Самовивіз";
  }
}

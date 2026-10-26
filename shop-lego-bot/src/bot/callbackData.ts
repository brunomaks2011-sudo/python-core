import type { OrderStatus, PaymentMethod } from "../generated/prisma/client.js";

/**
 * Формати callback_data для inline-кнопок (ліміт Telegram — 64 байти).
 * Частини розділяються двокрапкою; «_» означає порожнє значення.
 */

export type CheckoutEditField = "PRODUCT" | "QUANTITY" | "FULL_NAME" | "PHONE" | "CITY" | "DELIVERY_POINT" | "PAYMENT";

const PAYMENT_CODES: Record<PaymentMethod, string> = {
  CASH_ON_DELIVERY: "cod",
  CARD_TRANSFER: "card",
  BANK_TRANSFER: "bank",
};

export function paymentFromCode(code: string): PaymentMethod | null {
  const entry = Object.entries(PAYMENT_CODES).find(([, c]) => c === code);
  return entry ? (entry[0] as PaymentMethod) : null;
}

export interface ListQuery {
  themeKey?: string;
  minPrice?: number;
  maxPrice?: number;
  age?: number;
  condition?: "n" | "u";
  page: number;
}

const enc = (v: string | number | undefined) => (v === undefined || v === "" ? "_" : String(v));
const decNum = (v: string | undefined) => (v === undefined || v === "_" || v === "" ? undefined : Number(v));

export const cb = {
  // Покупець
  catalog: () => "cat",
  catalogAge: () => "cat:age",
  catalogPrice: () => "cat:price",
  list: (q: ListQuery) =>
    `ls:${enc(q.themeKey)}:${enc(q.minPrice)}:${enc(q.maxPrice)}:${enc(q.age)}:${enc(q.condition)}:${q.page}`,
  product: (id: number) => `pr:${id}`,
  buy: (id: number) => `buy:${id}`,
  similar: (id: number) => `sim:${id}`,
  checkoutQuantity: (nonce: number, n: number) => `ck:q:${nonce}:${n}`,
  checkoutPayment: (nonce: number, method: PaymentMethod) => `ck:pay:${nonce}:${PAYMENT_CODES[method]}`,
  checkoutReuse: (nonce: number, yes: boolean) => `ck:reuse:${nonce}:${yes ? "y" : "n"}`,
  checkoutConfirm: (nonce: number) => `ck:ok:${nonce}`,
  checkoutEdit: (nonce: number) => `ck:edit:${nonce}`,
  checkoutEditField: (nonce: number, field: CheckoutEditField) => `ck:ef:${nonce}:${field}`,
  checkoutSummary: (nonce: number) => `ck:sum:${nonce}`,
  checkoutCancel: (nonce: number) => `ck:x:${nonce}`,
  checkoutContinue: () => "ck:go",
  checkoutPick: (nonce: number, productId: number) => `ck:pick:${nonce}:${productId}`,
  myOrders: () => "mo",
  myOrder: (id: number) => `mo:${id}`,
  forgetMe: (yes: boolean) => `pv:forget:${yes ? "y" : "n"}`,
  help: () => "nav:help",

  // Адміністратор
  adminMenu: () => "a:menu",
  adminOrders: (filter: string, page: number) => `a:ol:${filter}:${page}`,
  adminOrder: (id: number) => `a:ov:${id}`,
  adminOrderStatus: (id: number, status: OrderStatus) => `a:os:${id}:${status}`,
  adminOrderStatusConfirm: (id: number, status: OrderStatus) => `a:os!:${id}:${status}`,
  adminResolveReturn: (id: number, restock: boolean) => `a:ors:${id}:${restock ? 1 : 0}`,
  adminProducts: (filter: string, page: number) => `a:pl:${filter}:${page}`,
  adminProduct: (id: number) => `a:pv:${id}`,
  adminProductEdit: (id: number, field: string) => `a:pe:${id}:${field}`,
  adminProductEnum: (id: number, field: string, value: string) => `a:pev:${id}:${field}:${value}`,
  adminProductArchive: (id: number) => `a:pa:${id}`,
  adminProductArchiveConfirm: (id: number) => `a:pa!:${id}`,
  adminProductRestore: (id: number) => `a:pr:${id}`,
  adminProductHistory: (id: number) => `a:ph:${id}`,
  adminProductStock: (id: number, mode: "add" | "sub") => `a:ps:${id}:${mode}`,
  adminNewProduct: () => "a:new",
  adminFindProduct: () => "a:find",
  adminWizard: (step: string, value: string) => `a:np:${step}:${value}`,
  adminWizardSave: () => "a:npok",
  adminWizardCancel: () => "a:npx",
  adminWizardRestart: () => "a:npre",
  adminCustomers: (page: number) => `a:cl:${page}`,
  adminCustomer: (id: number) => `a:cv:${id}`,
  adminBroadcastStart: () => "a:bc:new",
  adminBroadcastConfirm: () => "a:bc:ok",
  adminBroadcastCancel: () => "a:bc:x",
  adminStats: () => "a:st",
  adminCancelScene: () => "a:scx",
};

export function parseListQuery(parts: string[]): ListQuery {
  const [themeKey, minPrice, maxPrice, age, condition, page] = parts;
  return {
    themeKey: themeKey && themeKey !== "_" ? themeKey : undefined,
    minPrice: decNum(minPrice),
    maxPrice: decNum(maxPrice),
    age: decNum(age),
    condition: condition === "n" || condition === "u" ? condition : undefined,
    page: Math.max(1, decNum(page) ?? 1),
  };
}

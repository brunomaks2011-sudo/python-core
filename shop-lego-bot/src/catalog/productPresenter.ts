import type { BoxState, Completeness, Product, ProductCondition } from "../generated/prisma/client.js";
import { escapeHtml, formatMoney, truncate } from "../lib/format.js";
import type { ProductView } from "./productService.js";

type TitleSource = Pick<Product, "theme" | "setNumber" | "name">;

/** «LEGO Technic 42151 «Bugatti Bolide»» — без HTML-екранування. */
export function productTitle(p: TitleSource): string {
  const prefix = /lego/i.test(p.theme) ? p.theme : "LEGO";
  const number = p.setNumber ? ` ${p.setNumber}` : "";
  return `${prefix}${number} «${p.name}»`;
}

/** Коротка назва для кнопок і списків. */
export function productShortTitle(p: TitleSource, max = 48): string {
  return truncate(productTitle(p), max);
}

export const CONDITION_LABELS: Record<ProductCondition, string> = {
  NEW: "новий",
  USED: "вживаний",
};

export const BOX_LABELS: Record<BoxState, string> = {
  ORIGINAL: "в оригінальній коробці",
  DAMAGED: "коробка пошкоджена",
  NONE: "без коробки",
};

export const COMPLETENESS_LABELS: Record<Completeness, string> = {
  COMPLETE: "повний комплект",
  INCOMPLETE: "бракує частини деталей",
  UNCHECKED: "комплектність не перевірялася",
};

/** Стан товару одним рядком; відхилення від «нового в коробці» позначаються ⚠️. */
export function conditionText(p: Pick<Product, "condition" | "boxState" | "completeness">): string {
  const parts: string[] = [CONDITION_LABELS[p.condition]];
  parts.push(p.boxState === "ORIGINAL" ? BOX_LABELS.ORIGINAL : `⚠️ ${BOX_LABELS[p.boxState]}`);
  if (p.completeness === "INCOMPLETE") parts.push(`⚠️ ${COMPLETENESS_LABELS.INCOMPLETE}`);
  else if (p.completeness === "UNCHECKED") parts.push(COMPLETENESS_LABELS.UNCHECKED);
  else if (p.condition === "USED") parts.push(COMPLETENESS_LABELS.COMPLETE);
  return parts.join(", ");
}

export function availabilityLine(p: Pick<ProductView, "availability" | "available">): string {
  switch (p.availability) {
    case "IN_STOCK":
      return `✅ В наявності: ${p.available} шт.`;
    case "LOW_STOCK":
      return `⚠️ Залишилося мало: ${p.available} шт.`;
    default:
      return "❌ Немає в наявності";
  }
}

export function availabilityEmoji(p: Pick<ProductView, "availability">): string {
  return p.availability === "IN_STOCK" ? "✅" : p.availability === "LOW_STOCK" ? "⚠️ мало" : "❌ немає";
}

const NOT_SPECIFIED = "<i>не вказано</i>";

/** Картка товару для покупця (HTML). Показує лише дані з бази. */
export function productCard(p: ProductView, opts: { contact?: string; descriptionLimit?: number } = {}): string {
  const lines: string[] = [];
  lines.push(`🧱 <b>${escapeHtml(productTitle(p))}</b>`);
  lines.push("");
  lines.push(`Тематика: ${escapeHtml(p.theme)}`);
  lines.push(`Номер набору: ${p.setNumber ? escapeHtml(p.setNumber) : NOT_SPECIFIED}`);
  lines.push(`Кількість деталей: ${p.pieces ? p.pieces : NOT_SPECIFIED}`);
  lines.push(`Рекомендований вік: ${p.ageMin !== null ? `${p.ageMin}+` : NOT_SPECIFIED}`);
  lines.push(`Стан: ${conditionText(p)}`);
  if (p.conditionNote) lines.push(`Примітка щодо стану: ${escapeHtml(p.conditionNote)}`);
  lines.push("");
  lines.push(`💰 Ціна: <b>${formatMoney(p.price)}</b>`);
  lines.push(availabilityLine(p));
  if (p.description) {
    lines.push("");
    lines.push(escapeHtml(truncate(p.description, opts.descriptionLimit ?? 600)));
  }
  const missing = !p.setNumber || !p.pieces || p.ageMin === null;
  if (missing) {
    lines.push("");
    lines.push(
      `ℹ️ Дані, позначені «не вказано», відсутні в каталозі — уточніть у продавця${
        opts.contact ? `: ${escapeHtml(opts.contact)}` : ""
      }.`,
    );
  }
  return lines.join("\n");
}

/** Нумерований список товарів з цінами та наявністю (HTML). */
export function productListLines(items: ProductView[], startIndex = 1): string[] {
  return items.map(
    (p, i) =>
      `${startIndex + i}. ${escapeHtml(productShortTitle(p, 70))} — <b>${formatMoney(p.price)}</b> ${availabilityEmoji(p)}${
        p.condition === "USED" ? " (вживаний)" : ""
      }`,
  );
}

export const VERIFIED_NOTE = "✅ Ціни та наявність перевірено за каталогом магазину.";

/** Детальна картка для адміністратора: залишки, резерв, пороги. */
export function adminProductCard(p: ProductView): string {
  const lines = [
    `🧱 <b>${escapeHtml(productTitle(p))}</b>  <code>#${p.id}</code>`,
    p.status === "ARCHIVED" ? "🗄 <b>В архіві</b> (не показується покупцям)" : "🟢 Активний",
    "",
    `Тематика: ${escapeHtml(p.theme)}`,
    `Номер набору: ${p.setNumber ? escapeHtml(p.setNumber) : "—"}`,
    `Деталей: ${p.pieces ?? "—"}`,
    `Вік: ${p.ageMin !== null ? `${p.ageMin}+` : "—"}`,
    `Стан: ${CONDITION_LABELS[p.condition]}, ${BOX_LABELS[p.boxState]}, ${COMPLETENESS_LABELS[p.completeness]}`,
    `Примітка: ${p.conditionNote ? escapeHtml(p.conditionNote) : "—"}`,
    `Ціна: <b>${formatMoney(p.price)}</b>`,
    "",
    `📦 На складі: <b>${p.stockOnHand}</b>`,
    `🔒 У резерві: <b>${p.stockReserved}</b>`,
    `🛒 Доступно покупцям: <b>${p.available}</b> (поріг «мало»: ${p.lowStockThreshold})`,
    `Фото: ${p.telegramFileId ? "завантажене в Telegram" : p.imageUrl ? escapeHtml(truncate(p.imageUrl, 60)) : "—"}`,
    `Опис: ${p.description ? escapeHtml(truncate(p.description, 300)) : "—"}`,
  ];
  return lines.join("\n");
}

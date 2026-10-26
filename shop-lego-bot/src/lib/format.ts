/** Форматування тексту для Telegram (parse_mode: HTML) українською мовою. */

export type MoneyLike = number | string | { toString(): string };

const moneyFormatter = new Intl.NumberFormat("uk-UA", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export function toNumber(value: MoneyLike): number {
  return typeof value === "number" ? value : Number(value.toString());
}

/** 1800 → «1 800 грн», 1799.5 → «1 799,5 грн». */
export function formatMoney(value: MoneyLike): string {
  const n = toNumber(value);
  // Звичайний пробіл замість нерозривного — коректно відображається в усіх клієнтах Telegram.
  return `${moneyFormatter.format(n).replace(/ | /g, " ")} грн`;
}

export function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const pluralRules = new Intl.PluralRules("uk-UA");

/** Українські форми множини: pluralUk(5, "набір", "набори", "наборів") → «наборів». */
export function pluralUk(n: number, one: string, few: string, many: string): string {
  const rule = pluralRules.select(n);
  if (rule === "one") return one;
  if (rule === "few") return few;
  return many;
}

export function formatCount(n: number, one: string, few: string, many: string): string {
  return `${n} ${pluralUk(n, one, few, many)}`;
}

export function formatSets(n: number): string {
  return formatCount(n, "набір", "набори", "наборів");
}

export function formatDateTime(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("uk-UA", {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
    .format(date)
    .replace(",", "");
}

export function formatDate(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("uk-UA", {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

/** Обмеження Telegram: 4096 символів для тексту, 1024 — для підпису до фото. */
export const TELEGRAM_TEXT_LIMIT = 4096;
export const TELEGRAM_CAPTION_LIMIT = 1024;

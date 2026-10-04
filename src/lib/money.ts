// Робота з грошима. Усі суми в системі — цілі числа в копійках.

const uahFormatter = new Intl.NumberFormat("uk-UA", {
  style: "currency",
  currency: "UAH",
  currencyDisplay: "symbol",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

/** 129900 → «1 299 ₴» */
export function formatUAH(kopecks: number): string {
  return uahFormatter.format(kopecks / 100).replace("грн", "₴");
}

/** Гривні (можливо з копійками) → копійки. 12.5 → 1250 */
export function uahToKopecks(uah: number): number {
  return Math.round(uah * 100);
}

/** Копійки → рядок у гривнях з двома знаками після крапки (формат LiqPay). 1250 → "12.50" */
export function kopecksToUahString(kopecks: number): string {
  return (kopecks / 100).toFixed(2);
}

/** Відсоток знижки між старою і новою ціною (ціле число) або null. */
export function discountPercent(price: number, oldPrice: number | null | undefined): number | null {
  if (!oldPrice || oldPrice <= price) return null;
  return Math.round(((oldPrice - price) / oldPrice) * 100);
}

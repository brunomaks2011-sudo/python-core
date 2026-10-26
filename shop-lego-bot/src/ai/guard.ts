/**
 * Захист від «вигаданих» даних у відповіді мовної моделі.
 *
 * Будь-яке число у тексті відповіді (ціна, номер набору, кількість деталей, вік,
 * залишок, номер замовлення) має траплятися в перевірених джерелах: результатах
 * інструментів цього ходу, повідомленні покупця, контексті або налаштуваннях магазину.
 * Дрібні числа (до 10) дозволені — це нумерація, «2 набори» тощо.
 */

const NUMBER_RE = /\d(?:[\d   ]*\d)?(?:[.,]\d{1,2})?/g;

/** Нормалізує число: «1 800» → «1800», «1799,50» → «1799.5», «1800.00» → «1800». */
export function normalizeNumber(raw: string): string {
  const compact = raw.replace(/[\s  ]/g, "").replace(",", ".");
  const n = Number(compact);
  if (!Number.isFinite(n)) return compact;
  return String(n);
}

/** Усі числа з тексту в нормалізованому вигляді (включно з окремими групами цифр). */
export function extractNumbers(text: string): string[] {
  const result = new Set<string>();
  for (const m of text.matchAll(NUMBER_RE)) {
    const raw = m[0];
    result.add(normalizeNumber(raw));
    // «2 2 набори» чи «1 800» — додаємо також окремі групи на випадок неоднозначності
    for (const part of raw.split(/[\s  ]+/)) {
      if (part) result.add(normalizeNumber(part));
    }
  }
  return [...result];
}

export class NumberWhitelist {
  private readonly allowed = new Set<string>();

  addText(text: string | null | undefined): void {
    if (!text) return;
    for (const n of extractNumbers(text)) this.allowed.add(n);
  }

  has(n: string): boolean {
    return this.allowed.has(n);
  }
}

/** Повертає числа з відповіді, яких немає в перевірених джерелах. */
export function findUnverifiedNumbers(answer: string, whitelist: NumberWhitelist): string[] {
  const unverified: string[] = [];
  for (const m of answer.matchAll(NUMBER_RE)) {
    const full = normalizeNumber(m[0]);
    if (whitelist.has(full)) continue;
    const parts = m[0].split(/[\s  ]+/).filter(Boolean).map(normalizeNumber);
    // «2 набори по 1800» може злитися в «2 1800» — приймаємо, якщо кожна частина перевірена або дрібна
    const partsOk = parts.length > 1 && parts.every((p) => whitelist.has(p) || Number(p) <= 10);
    if (partsOk) continue;
    if (Number(full) <= 10) continue;
    unverified.push(full);
  }
  return unverified;
}

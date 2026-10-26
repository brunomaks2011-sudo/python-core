import { cleanInput } from "./text.js";

export type ValidationResult<T> = { ok: true; value: T } | { ok: false; error: string };

const ok = <T>(value: T): ValidationResult<T> => ({ ok: true, value });
const fail = <T>(error: string): ValidationResult<T> => ({ ok: false, error });

/**
 * Нормалізує номер телефону. Українські номери → +380XXXXXXXXX.
 * Міжнародні номери приймаються у форматі +<код країни><номер> (10–15 цифр).
 */
export function normalizePhone(input: string): ValidationResult<string> {
  const raw = cleanInput(input);
  if (!/^[+\d\s()\-.]{9,25}$/.test(raw)) {
    return fail("Номер телефону має містити лише цифри, наприклад: +380 67 123 45 67");
  }
  const digits = raw.replace(/\D/g, "");
  if (digits.length === 12 && digits.startsWith("380")) return ok(`+${digits}`);
  if (digits.length === 10 && digits.startsWith("0")) return ok(`+38${digits}`);
  if (digits.length === 9 && !raw.startsWith("+")) return ok(`+380${digits}`);
  if (raw.startsWith("+") && digits.length >= 10 && digits.length <= 15 && !digits.startsWith("380")) {
    return ok(`+${digits}`);
  }
  return fail("Не вдалося розпізнати номер. Введіть його у форматі +380 67 123 45 67 або 067 123 45 67");
}

const NAME_PART = /^[\p{L}][\p{L}'’ʼ\-.]*$/u;

export function validateFullName(input: string): ValidationResult<string> {
  const value = cleanInput(input).replace(/[’ʼ`]/g, "'");
  if (value.length < 3 || value.length > 80) {
    return fail("Вкажіть ім’я та прізвище (від 3 до 80 символів), наприклад: Іван Петренко");
  }
  if (/\d/.test(value)) return fail("Ім’я та прізвище не можуть містити цифр");
  const parts = value.split(" ").filter(Boolean);
  if (parts.length < 2) return fail("Будь ласка, вкажіть і ім’я, і прізвище, наприклад: Іван Петренко");
  if (parts.length > 4 || !parts.every((p) => NAME_PART.test(p) && p.length >= 1)) {
    return fail("Ім’я та прізвище можуть містити лише літери, апостроф і дефіс");
  }
  return ok(parts.map((p) => p.charAt(0).toLocaleUpperCase("uk-UA") + p.slice(1)).join(" "));
}

export function validateCity(input: string): ValidationResult<string> {
  const value = cleanInput(input).replace(/[’ʼ`]/g, "'");
  if (value.length < 2 || value.length > 60) return fail("Вкажіть назву населеного пункту (від 2 до 60 символів)");
  if (!/^[\p{L}][\p{L}\s'\-.,()]*$/u.test(value)) {
    return fail("Назва населеного пункту може містити лише літери, пробіли, апостроф, дефіс і крапку");
  }
  return ok(value.charAt(0).toLocaleUpperCase("uk-UA") + value.slice(1));
}

export function validateDeliveryPoint(input: string): ValidationResult<string> {
  const value = cleanInput(input).replace(/\n+/g, ", ");
  if (value.length < 1 || value.length > 200) return fail("Вкажіть номер відділення або адресу (до 200 символів)");
  if (/^\d{1,6}$/.test(value)) return ok(`Відділення №${value}`);
  if (!/[\p{L}\d]/u.test(value)) return fail("Вкажіть номер відділення або адресу");
  return ok(value);
}

/** Ціна у гривнях: «1800», «1 800», «1799.50», «1799,5 грн». */
export function parsePrice(input: string): ValidationResult<string> {
  const value = cleanInput(input)
    .toLowerCase()
    .replace(/грн\.?|₴|uah/g, "")
    .replace(/[\s ]/g, "")
    .replace(",", ".");
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(value)) return fail("Введіть ціну числом, наприклад: 1800 або 1799.50");
  const n = Number(value);
  if (!(n > 0)) return fail("Ціна має бути більшою за нуль");
  if (n > 10_000_000) return fail("Занадто велика ціна");
  return ok(n.toFixed(2));
}

export function parseNonNegativeInt(input: string, max = 1_000_000): ValidationResult<number> {
  const value = cleanInput(input).replace(/\s/g, "");
  if (!/^\d{1,9}$/.test(value)) return fail("Введіть ціле число, наприклад: 5");
  const n = Number(value);
  if (n > max) return fail(`Число не може бути більшим за ${max}`);
  return ok(n);
}

export function parsePositiveInt(input: string, max = 1_000_000): ValidationResult<number> {
  const r = parseNonNegativeInt(input, max);
  if (!r.ok) return r;
  if (r.value === 0) return fail("Число має бути більшим за нуль");
  return r;
}

/** Зміна залишку: «+3», «-2», «3». */
export function parseSignedInt(input: string, maxAbs = 100_000): ValidationResult<number> {
  const value = cleanInput(input).replace(/\s/g, "");
  if (!/^[+-]?\d{1,7}$/.test(value)) return fail("Введіть число зі знаком, наприклад: +3 або -1");
  const n = Number(value);
  if (n === 0) return fail("Зміна не може дорівнювати нулю");
  if (Math.abs(n) > maxAbs) return fail("Занадто велике значення");
  return ok(n);
}

export function validateSetNumber(input: string): ValidationResult<string> {
  const value = cleanInput(input).replace(/^#|^№/, "").trim();
  if (!/^[A-Za-z0-9-]{2,20}$/.test(value)) {
    return fail("Номер набору може містити лише цифри, латинські літери й дефіс (наприклад: 42151 або 75192-1)");
  }
  return ok(value.replace(/-1$/, ""));
}

export function validateProductName(input: string): ValidationResult<string> {
  const value = cleanInput(input);
  if (value.length < 2 || value.length > 120) return fail("Назва має містити від 2 до 120 символів");
  return ok(value);
}

export function validateTheme(input: string): ValidationResult<string> {
  const value = cleanInput(input);
  if (value.length < 2 || value.length > 60) return fail("Тематика має містити від 2 до 60 символів");
  return ok(value);
}

export function validateLongText(input: string, max = 2000): ValidationResult<string> {
  const value = input.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "").trim();
  if (value.length < 1) return fail("Текст не може бути порожнім");
  if (value.length > max) return fail(`Текст задовгий (максимум ${max} символів)`);
  return ok(value);
}

export function validateImageUrl(input: string): ValidationResult<string> {
  const value = cleanInput(input);
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" && url.protocol !== "http:") return fail("Посилання має починатися з https://");
    return ok(url.toString());
  } catch {
    return fail("Некоректне посилання на зображення");
  }
}

export function validateTrackingNumber(input: string): ValidationResult<string> {
  const value = cleanInput(input).replace(/\s/g, "");
  if (!/^[A-Za-z0-9-]{5,40}$/.test(value)) return fail("Номер ТТН має містити 5–40 цифр або латинських літер");
  return ok(value);
}

/** Розбір української розмовної мови: нормалізація, числа словами, ціни, вік. */

const APOSTROPHES = /[’ʼ`´‘]/g;

/** Нижній регістр, єдиний апостроф, без зайвих знаків і пробілів. */
export function normalizeText(input: string): string {
  return input
    .toLowerCase()
    .replace(APOSTROPHES, "'")
    .replace(/ё/g, "е")
    .replace(/[^\p{L}\p{N}'+\-.,\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Прибирає керувальні символи й зайві пробіли з введення користувача. */
export function cleanInput(input: string): string {
  return input
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .replace(/[ \t]+/g, " ")
    .trim();
}

const TRANSLIT: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "h", ґ: "g", д: "d", е: "e", є: "ie", ж: "zh", з: "z", и: "y", і: "i",
  ї: "i", й: "i", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u",
  ф: "f", х: "kh", ц: "ts", ч: "ch", ш: "sh", щ: "shch", ь: "", ю: "iu", я: "ia", "'": "",
  ы: "y", э: "e", ъ: "",
};

/**
 * Транслітерація кирилиці латиницею у двох варіантах (г→h та г→g, и→y та и→i),
 * щоб «бугатті» знаходило «Bugatti», а «мілленіум» — «Millennium».
 */
export function transliterationVariants(word: string): string[] {
  if (!/[а-яіїєґё]/i.test(word)) return [];
  const lower = word.toLowerCase();
  const official = [...lower].map((ch) => TRANSLIT[ch] ?? ch).join("");
  const popular = [...lower]
    .map((ch) => (ch === "г" ? "g" : ch === "и" ? "i" : ch === "х" ? "h" : (TRANSLIT[ch] ?? ch)))
    .join("");
  return [...new Set([official, popular])].filter((v) => v.length >= 3);
}

const UNITS: Array<[RegExp, number]> = [
  [/^(один|одна|одне|одного|одну|одній|одним)$/, 1],
  [/^(два|дві|двох|двома|двоє)$/, 2],
  [/^(три|трьох|трьома|троє)$/, 3],
  [/^(чотири|чотирьох|чотирма|четверо)$/, 4],
  [/^(п'ять|пять|п'яти|пяти|п'ятьох|п'ятеро)$/, 5],
  [/^(шість|шести|шістьох|шестеро)$/, 6],
  [/^(сім|семи|сімох|семеро)$/, 7],
  [/^(вісім|восьми|вісьмох)$/, 8],
  [/^(дев'ять|девять|дев'яти|девяти)$/, 9],
  [/^(десять|десяти|десятьох)$/, 10],
  [/^(одинадцять|одинадцяти)$/, 11],
  [/^(дванадцять|дванадцяти)$/, 12],
  [/^(тринадцять|тринадцяти)$/, 13],
  [/^(чотирнадцять|чотирнадцяти)$/, 14],
  [/^(п'ятнадцять|пятнадцять|п'ятнадцяти)$/, 15],
  [/^(шістнадцять|шістнадцяти)$/, 16],
  [/^(сімнадцять|сімнадцяти)$/, 17],
  [/^(вісімнадцять|вісімнадцяти)$/, 18],
  [/^(дев'ятнадцять|дев'ятнадцяти)$/, 19],
  [/^(двадцять|двадцяти)$/, 20],
  [/^(тридцять|тридцяти)$/, 30],
  [/^(сорок|сорока)$/, 40],
  [/^(п'ятдесят|пятдесят|п'ятдесяти)$/, 50],
  [/^(шістдесят|шістдесяти)$/, 60],
  [/^(сімдесят|сімдесяти)$/, 70],
  [/^(вісімдесят|вісімдесяти)$/, 80],
  [/^(дев'яносто)$/, 90],
  [/^(сто|ста)$/, 100],
  [/^(двісті|двохсот)$/, 200],
  [/^(триста|трьохсот)$/, 300],
  [/^(чотириста|чотирьохсот)$/, 400],
  [/^(п'ятсот|пятсот|п'ятисот)$/, 500],
  [/^(шістсот|шестисот)$/, 600],
  [/^(сімсот|семисот)$/, 700],
  [/^(вісімсот|восьмисот)$/, 800],
  [/^(дев'ятсот|дев'ятисот)$/, 900],
];

const THOUSAND = /^(тисяча|тисячі|тисяч|тисячу|тис|тис\.|тыс|k|к)$/;

function wordValue(word: string): number | null {
  for (const [re, value] of UNITS) if (re.test(word)) return value;
  return null;
}

/**
 * Перетворює числа словами на цифри в тексті:
 * «до двох тисяч» → «до 2000», «півтори тисячі» → «1500», «2к» → «2000», «2,5 тис» → «2500».
 */
export function replaceNumberWords(input: string): string {
  let text = normalizeText(input);
  // «2к», «2k», «2.5к», «2,5 тис»
  text = text.replace(/(\d+(?:[.,]\d+)?)\s?(к|k|тис\.?|тисяч[аі]?|тисячу)(?![\p{L}])/gu, (_, num: string) =>
    String(Math.round(Number(num.replace(",", ".")) * 1000)),
  );
  text = text.replace(/півтори\s+тисяч[іи]?/g, "1500").replace(/пів\s?тисяч[іи]/g, "500");

  const tokens = text.split(" ");
  const out: string[] = [];
  let i = 0;
  while (i < tokens.length) {
    const token = tokens[i] ?? "";
    let value = wordValue(token);
    if (value === null) {
      out.push(token);
      i += 1;
      continue;
    }
    // Складені числа: «двісті п'ятдесят», «дві тисячі п'ятсот»
    let total = 0;
    let current = value;
    let j = i + 1;
    while (j < tokens.length) {
      const next = tokens[j] ?? "";
      if (THOUSAND.test(next)) {
        total += (current || 1) * 1000;
        current = 0;
        j += 1;
        continue;
      }
      const nextValue = wordValue(next);
      if (nextValue !== null && nextValue < (current === 0 ? 1000 : current)) {
        current += nextValue;
        j += 1;
        continue;
      }
      break;
    }
    value = total + current;
    out.push(String(value));
    i = j;
  }
  // «тисяча»/«тисячу» без числа перед ними
  return out
    .join(" ")
    .replace(/(^|\s)(тисяча|тисячу)(?=\s|$)/g, "$11000")
    .replace(/(\d)\s(\d{3})(?!\d)/g, "$1$2"); // «2 000» → «2000»
}

export interface PriceRange {
  min?: number;
  max?: number;
}

/** Розпізнає цінові обмеження: «до 2000 грн», «від 1000 до 3000», «за 1500», «дешевше двох тисяч». */
export function parsePriceRange(input: string): PriceRange | null {
  const text = replaceNumberWords(input);
  const num = String.raw`(\d{2,7}(?:[.,]\d{1,2})?)`;
  const money = String.raw`\s*(?:грн|гривень|гривні|гривня|₴|uah|грив)?`;
  const toNumber = (s: string) => Number(s.replace(",", "."));

  const between = new RegExp(String.raw`(?:від|вiд|з)\s*${num}${money}\s*(?:до|по|-|–)\s*${num}`, "u").exec(text);
  if (between?.[1] && between[2]) {
    const a = toNumber(between[1]);
    const b = toNumber(between[2]);
    return { min: Math.min(a, b), max: Math.max(a, b) };
  }
  const dash = new RegExp(String.raw`${num}\s*(?:-|–)\s*${num}\s*(?:грн|гривень|₴)`, "u").exec(text);
  if (dash?.[1] && dash[2]) {
    const a = toNumber(dash[1]);
    const b = toNumber(dash[2]);
    return { min: Math.min(a, b), max: Math.max(a, b) };
  }
  const max = new RegExp(
    String.raw`(?:до|не\s+дорожче|дешевше|дешевші|менше|максимум|не\s+більше|в\s+межах|у\s+межах|бюджет|за)\s*${num}`,
    "u",
  ).exec(text);
  const min = new RegExp(String.raw`(?:від|вiд|дорожче|дорожчі|більше|мінімум|не\s+менше)\s*${num}${money}`, "u").exec(text);
  const result: PriceRange = {};
  if (max?.[1]) result.max = toNumber(max[1]);
  if (min?.[1]) {
    // «від 8 років» — це вік, а не ціна
    const after = text.slice(min.index + min[0].length, min.index + min[0].length + 8);
    if (!/^\s*(рок|рік|р\.|\+)/.test(after)) result.min = toNumber(min[1]);
  }
  if (result.max === undefined && result.min === undefined) {
    const plain = new RegExp(String.raw`${num}\s*(?:грн|гривень|гривні|₴|uah)`, "u").exec(text);
    if (plain?.[1]) result.max = toNumber(plain[1]);
  }
  if (result.max !== undefined && result.max < 50) delete result.max;
  if (result.min !== undefined && result.min < 50) delete result.min;
  return result.max !== undefined || result.min !== undefined ? result : null;
}

/** Вік дитини: «від 8 років», «дитині 10 років», «8+», «семирічному». */
export function parseChildAge(input: string): number | null {
  const text = replaceNumberWords(input);
  const patterns = [
    /(?:від|вiд|з|на|для)\s*(\d{1,2})\s*(?:\+|років|роки|рік|р\.|річн)/u,
    /(\d{1,2})\s*(?:\+|років|роки|рік|річн)/u,
    /(?:вік|віку)\s*(\d{1,2})/u,
  ];
  for (const re of patterns) {
    const m = re.exec(text);
    if (m?.[1]) {
      const age = Number(m[1]);
      if (age >= 1 && age <= 99) return age;
    }
  }
  const adjectives: Array<[RegExp, number]> = [
    [/дворічн/, 2], [/трирічн/, 3], [/чотирирічн/, 4], [/п'ятирічн/, 5], [/шестирічн/, 6],
    [/семирічн/, 7], [/восьмирічн/, 8], [/дев'ятирічн/, 9], [/десятирічн/, 10], [/дванадцятирічн/, 12],
  ];
  for (const [re, age] of adjectives) if (re.test(text)) return age;
  return null;
}

/** Номер набору LEGO: 3–7 цифр, можливо з суфіксом версії «-1». */
export function extractSetNumbers(input: string): string[] {
  const text = replaceNumberWords(input);
  const result = new Set<string>();
  const re = /(?<!\d|\d[.,])(\d{3,7})(?:-\d)?(?!\d|[.,]\d|\s*(?:грн|гривень|гривні|₴|uah|років|роки|рік|\+))/gu;
  for (const m of text.matchAll(re)) {
    const value = m[1];
    if (!value) continue;
    const before = text.slice(Math.max(0, (m.index ?? 0) - 12), m.index ?? 0);
    // числа після «до/від/за» — це ціни
    if (/(до|від|вiд|за|дешевше|дорожче|менше|більше|максимум|бюджет)\s*$/.test(before)) continue;
    result.add(value);
  }
  return [...result];
}

/** Кількість: «2», «два», «2 шт», «дві штуки». */
export function parseQuantity(input: string): number | null {
  const text = replaceNumberWords(input);
  const m = /^(\d{1,3})\s*(?:шт\.?|штук[иа]?|набор[иів]*|набір)?$/u.exec(text.trim());
  if (!m?.[1]) return null;
  const n = Number(m[1]);
  return Number.isInteger(n) && n > 0 ? n : null;
}

const QUESTION_START =
  /^(чи|а|є|скільки|що|як|коли|де|чому|покажи|покажіть|шукаю|хочу|можна|підкажіть|підкажи|порадьте|порадь|дайте|які|який|яка|яке|у вас|в вас|а у вас|есть|сколько|какие|покажите)(\s|\?|$)/u;

/** Чи схоже повідомлення на запитання/запит, а не на відповідь на крок оформлення. */
export function looksLikeQuestion(input: string): boolean {
  const text = normalizeText(input);
  if (input.includes("?")) return true;
  return QUESTION_START.test(text);
}

import { createHash } from "node:crypto";
import { normalizeText } from "../lib/text.js";

/**
 * Відомі тематики LEGO та розмовні варіанти їхніх назв.
 * Аліаси з позначкою «*» шукаються як початок слова («технік*» → «техніку», «техніки»),
 * решта — як окремі слова чи фрази.
 */
interface ThemeDefinition {
  name: string;
  /** Частина назви, за якою шукаємо в полі theme товарів (без регістру). */
  match: string;
  aliases: string[];
}

export const KNOWN_THEMES: ThemeDefinition[] = [
  { name: "LEGO City", match: "city", aliases: ["city", "сіті", "сити", "сіті*", "лего місто", "lego city"] },
  {
    name: "LEGO Technic",
    match: "technic",
    aliases: ["technic*", "technik*", "технік*", "техник*", "технiк*", "техніка", "техніку"],
  },
  {
    name: "LEGO Star Wars",
    match: "star wars",
    aliases: [
      "star wars", "starwars", "стар варс", "старварс", "стар ворс", "зоряні війни", "зоряних війн",
      "зоряних воєн", "зоряні воєн", "зоряних війнах", "звездные войны", "звёздные войны", "звездных войн",
    ],
  },
  {
    name: "LEGO Harry Potter",
    match: "harry potter",
    aliases: ["harry potter", "гаррі поттер*", "гарі потер*", "гарри поттер*", "поттер*", "хогвартс*", "hogwarts"],
  },
  { name: "LEGO Icons", match: "icons", aliases: ["icons", "айконс", "айкон*", "creator expert", "креатор експерт"] },
  { name: "LEGO Creator", match: "creator", aliases: ["creator", "креатор*", "кріейтор*", "3 в 1", "3в1", "3-in-1"] },
  { name: "LEGO Friends", match: "friends", aliases: ["friends", "френдс", "френдс", "подружки", "лего для дівчат"] },
  { name: "LEGO Ninjago", match: "ninjago", aliases: ["ninjago", "ніндзяго", "ниндзяго", "ніндзя*", "ниндзя*"] },
  {
    name: "LEGO Marvel",
    match: "marvel",
    aliases: ["marvel", "марвел*", "супергеро*", "месник*", "мстител*", "avengers", "людина-павук", "спайдермен*"],
  },
  { name: "LEGO DC", match: "dc", aliases: ["dc", "бетмен*", "бэтмен*", "batman", "супермен*"] },
  { name: "LEGO DUPLO", match: "duplo", aliases: ["duplo", "дупло", "для малюків", "для малечі"] },
  { name: "LEGO Classic", match: "classic", aliases: ["classic", "класик*", "класік*"] },
  { name: "LEGO Ideas", match: "ideas", aliases: ["ideas", "ідеас", "айдіас", "идеас"] },
  { name: "LEGO Architecture", match: "architecture", aliases: ["architecture", "архітектур*", "архитектур*"] },
  { name: "LEGO Minecraft", match: "minecraft", aliases: ["minecraft", "майнкрафт*", "майн крафт*"] },
  {
    name: "LEGO Speed Champions",
    match: "speed champions",
    aliases: ["speed champions", "спід чемпіонс", "спид чемпионс", "спідчемпіонс"],
  },
  { name: "LEGO Disney", match: "disney", aliases: ["disney", "дісней*", "дисней*", "принцес*"] },
  { name: "LEGO Super Mario", match: "mario", aliases: ["super mario", "маріо", "марио", "mario"] },
  { name: "LEGO Botanicals", match: "botanical", aliases: ["botanical*", "ботанікал*", "квіти", "квітів", "букет*"] },
  { name: "LEGO Jurassic World", match: "jurassic", aliases: ["jurassic*", "юрськ*", "динозавр*"] },
  { name: "LEGO Dreamzzz", match: "dreamzzz", aliases: ["dreamzzz", "дрімз*"] },
  { name: "LEGO Sonic", match: "sonic", aliases: ["sonic", "сонік*", "соник*"] },
  { name: "LEGO Avatar", match: "avatar", aliases: ["avatar", "аватар*"] },
  { name: "LEGO Art", match: "lego art", aliases: ["lego art", "лего арт"] },
  { name: "LEGO Wednesday", match: "wednesday", aliases: ["wednesday", "венздей", "венсдей"] },
];

/** Кнопки тематик у майстрі додавання товару. */
export const THEME_SUGGESTIONS = KNOWN_THEMES.slice(0, 18).map((t) => t.name);

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const compiled = KNOWN_THEMES.map((theme) => ({
  theme,
  patterns: theme.aliases.map((alias) => {
    const prefix = alias.endsWith("*");
    const body = escapeRegExp(normalizeText(prefix ? alias.slice(0, -1) : alias));
    return new RegExp(`(?<![\\p{L}\\p{N}])${body}${prefix ? "" : "(?![\\p{L}\\p{N}])"}`, "u");
  }),
}));

export interface ThemeMatch {
  name: string;
  match: string;
  /** Нормалізований текст запиту без знайденої назви тематики. */
  rest: string;
}

/** Шукає відому тематику в довільному тексті покупця. */
export function detectTheme(input: string): ThemeMatch | null {
  const text = normalizeText(input);
  for (const { theme, patterns } of compiled) {
    for (const re of patterns) {
      const m = re.exec(text);
      if (m) {
        // прибираємо все слово, в якому знайдено аліас
        const start = m.index;
        let end = m.index + m[0].length;
        while (end < text.length && /[\p{L}\p{N}]/u.test(text.charAt(end))) end += 1;
        const rest = `${text.slice(0, start)} ${text.slice(end)}`.replace(/\s+/g, " ").trim();
        return { name: theme.name, match: theme.match, rest };
      }
    }
  }
  return null;
}

/**
 * Перетворює назву тематики від покупця, адміністратора чи моделі на шаблон пошуку:
 * «технік» → «technic», «LEGO Star Wars» → «star wars», «Інше» → «інше».
 */
export function themeSearchPattern(input: string): string {
  const detected = detectTheme(input);
  if (detected) return detected.match;
  return normalizeText(input).replace(/^lego\s+/, "").trim();
}

/** Короткий стабільний ідентифікатор тематики для callback-кнопок (ліміт Telegram — 64 байти). */
export function themeKey(theme: string): string {
  return createHash("sha1").update(theme.toLowerCase()).digest("hex").slice(0, 8);
}

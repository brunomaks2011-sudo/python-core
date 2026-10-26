import type { ProductCondition } from "../generated/prisma/client.js";
import { detectTheme } from "../catalog/themes.js";
import { searchTokens } from "../catalog/productService.js";
import {
  extractSetNumbers,
  normalizeText,
  parseChildAge,
  parsePriceRange,
  replaceNumberWords,
} from "../lib/text.js";

/**
 * Резервний (без ШІ) розбір повідомлень покупця. Використовується, коли Claude API
 * вимкнено, недоступне або перевищено ліміт запитів. Покриває типові запити:
 * пошук за тематикою, ціною, віком і номером набору, «цей набір», замовлення,
 * історію покупок, доставку й оплату.
 */

export interface SearchIntentFilters {
  text: string | null;
  theme: string | null;
  minPrice: number | null;
  maxPrice: number | null;
  childAge: number | null;
  condition: ProductCondition | null;
}

export type Intent =
  | { type: "thanks" }
  | { type: "help" }
  | { type: "catalog" }
  | { type: "my_orders" }
  | { type: "shop_info"; topic: "delivery" | "payment" | "contacts" | "hours" }
  | { type: "order"; setNumber: string | null; quantity: number | null }
  | { type: "product_lookup"; setNumbers: string[] }
  | { type: "about_last_shown"; aspect: "price" | "availability" | "details" | "similar" }
  | { type: "search"; filters: SearchIntentFilters }
  | { type: "greeting_only" }
  | { type: "unknown" };

export interface ParsedMessage {
  greeting: boolean;
  intent: Intent;
}

const GREETING =
  /^(привіт(ик)?|вітаю|добр(ий|ого)\s+(день|вечір|вечора|ранку|ранок)|доброго\s+дня|здрастуйте|здравствуйте|hello|hi|хай|салют|добрый день|привет)[\s!,.)]*/u;
const THANKS = /^(дякую|дякую вам|дякс|спасибі|спасибо|thanks|thank you|супер,? дякую)/u;
const HELP = /^(допомога|help|що ти вмієш|що ви вмієте|як (це )?працює|команди)/u;
const MY_ORDERS =
  /(мо[їі]\s+замовлення|мо[їі]\s+покупки|мо[єе]\s+замовлення|що я замовляв|що я купував|(я|ми)\s+вже\s+(у|в)?\s*вас\s+купував|я\s+вже\s+купував|раніше\s+купував|статус\s+(мого\s+)?замовлення|де\s+мо[єе]\s+замовлення|історі[яю]\s+(замовлень|покупок))/u;
const DELIVERY = /(доставк|відправ|нова\s*пошта|новою\s*поштою|укрпошт|поштомат|самовивіз|скільки\s+їде)/u;
const PAYMENT = /(оплат|оплачу|накладен|реквізит|передплат|розрахун|карт(у|ою|ка)\s)/u;
const CONTACTS = /(контакт|зв'яз|менеджер|продав(ець|цю|ця)|оператор|людин(а|ою|і)|номер\s+телефону\s+магазину)/u;
const HOURS = /(графік|години\s+роботи|коли\s+працюєте|до\s+котрої|робочі\s+години)/u;
const ORDER =
  /(замовити|замовлю|замовляю|купити|куплю|купую|оформити|оформлю|придбати|беру|візьму|хочу\s+(його|цей|ці|це|такий))/u;
const THIS_ONE = /(цей|цього|ця|цю|це|ці|його|він|вона|такий|такого)/u;
const PRICE_Q = /(скільки\s+(коштує|коштують|буде|за)|ціна|ціну|вартість|почім|по\s+чому)/u;
const AVAIL_Q = /(є\s+в\s+наявності|в\s+наявності|наявн|залишил|чи\s+є|є\s*\?|ще\s+є|є\s+ще)/u;
const SIMILAR = /(схож|подібн|аналог|щось\s+таке\s+ж|інші\s+варіанти)/u;
const CATALOG =
  /^(каталог|асортимент|що\s+(у\s+вас\s+)?є|що\s+є\s+в\s+наявності|всі\s+набори|усі\s+набори|покажи\s+(все|усе|всі|каталог)|що\s+можна\s+купити)\s*\??$/u;
const USED = /(вживан|б\/у|(?<!\p{L})бу(?!\p{L})|секонд|не\s+нов)/u;

function parseQuantityPhrase(text: string): number | null {
  const m = /(\d{1,2})\s*(шт|штук|набор|набір|коробк|екземпляр)/u.exec(text);
  if (m?.[1]) {
    const n = Number(m[1]);
    return n > 0 && n <= 100 ? n : null;
  }
  return null;
}

export function parseMessage(input: string, ctx: { hasLastShown: boolean }): ParsedMessage {
  const original = normalizeText(input);
  const greetingMatch = GREETING.exec(original);
  const greeting = Boolean(greetingMatch);
  const rawRest = greetingMatch ? input.slice(Math.min(input.length, greetingMatch[0].length)) : input;
  const text = normalizeText(replaceNumberWords(greetingMatch ? original.slice(greetingMatch[0].length) : input));
  const intent = parseIntent(text, rawRest, ctx);
  if (greeting && intent.type === "unknown" && text.replace(/[!?.\s]/g, "").length === 0) {
    return { greeting, intent: { type: "greeting_only" } };
  }
  return { greeting, intent };
}

function parseIntent(text: string, raw: string, ctx: { hasLastShown: boolean }): Intent {
  if (!text) return { type: "unknown" };
  if (THANKS.test(text)) return { type: "thanks" };
  if (HELP.test(text)) return { type: "help" };
  if (MY_ORDERS.test(text)) return { type: "my_orders" };

  const setNumbers = extractSetNumbers(raw);
  const priceInText = parsePriceRange(text);
  // «Що можна купити за 1500 грн?» — це пошук за бюджетом, а не замовлення
  const budgetQuestion = priceInText !== null || /^(що|які|який)\s+(можна\s+|варто\s+)?купити/u.test(text);
  if (ORDER.test(text) && !budgetQuestion) {
    return { type: "order", setNumber: setNumbers[0] ?? null, quantity: parseQuantityPhrase(text) };
  }
  if (DELIVERY.test(text)) return { type: "shop_info", topic: "delivery" };
  if (PAYMENT.test(text) && !/грн/u.test(text)) return { type: "shop_info", topic: "payment" };
  if (HOURS.test(text)) return { type: "shop_info", topic: "hours" };
  if (CONTACTS.test(text)) return { type: "shop_info", topic: "contacts" };
  if (setNumbers.length > 0) return { type: "product_lookup", setNumbers };
  if (CATALOG.test(text)) return { type: "catalog" };

  const theme = detectTheme(text);
  const price = parsePriceRange(text);
  const childAge = parseChildAge(text);
  const condition: ProductCondition | null = USED.test(text) ? "USED" : null;

  if (ctx.hasLastShown && !theme && !price && childAge === null) {
    if (SIMILAR.test(text)) return { type: "about_last_shown", aspect: "similar" };
    if (THIS_ONE.test(text) || PRICE_Q.test(text) || AVAIL_Q.test(text)) {
      if (PRICE_Q.test(text)) return { type: "about_last_shown", aspect: "price" };
      if (AVAIL_Q.test(text)) return { type: "about_last_shown", aspect: "availability" };
      return { type: "about_last_shown", aspect: "details" };
    }
  }

  const rest = theme ? theme.rest : text;
  const leftover = searchTokens(stripFilterWords(rest)).join(" ");
  if (theme || price || childAge !== null || condition || leftover) {
    return {
      type: "search",
      filters: {
        text: leftover || null,
        theme: theme?.name ?? null,
        minPrice: price?.min ?? null,
        maxPrice: price?.max ?? null,
        childAge,
        condition,
      },
    };
  }
  return { type: "unknown" };
}

/** Прибирає з тексту слова, що вже враховані фільтрами (ціна, вік, стан). */
function stripFilterWords(text: string): string {
  return text
    .replace(/(до|від|за|дешевше|дорожче|менше|більше|максимум|бюджет|в межах)\s*\d+(\s*(грн|гривень|гривні|₴))?/gu, " ")
    .replace(/\d+\s*(грн|гривень|гривні|₴)/gu, " ")
    .replace(/(від|для|на)?\s*\d{1,2}\s*(\+|років|роки|рік|річн\S*)/gu, " ")
    .replace(USED, " ")
    .replace(/(?<!\p{L})(дит\S*|хлопч\S*|дівч\S*|син\S*|доньк\S*|онук\S*|подаруно\S*|подарувати|подарунк\S*|що|можна|купити|тисяч\S*)(?!\p{L})/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

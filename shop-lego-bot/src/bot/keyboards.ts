import { Markup } from "telegraf";
import type { InlineKeyboardButton } from "telegraf/types";

export const MENU = {
  catalog: "🧱 Каталог",
  search: "🔎 Пошук набору",
  myOrders: "📦 Мої замовлення",
  help: "ℹ️ Допомога",
  contact: "📞 Зв’язатися з продавцем",
  admin: "⚙️ Адмін-панель",
} as const;

export function mainMenu(isAdmin: boolean) {
  const rows: string[][] = [
    [MENU.catalog, MENU.search],
    [MENU.myOrders, MENU.help],
  ];
  if (isAdmin) rows.push([MENU.admin]);
  return Markup.keyboard(rows).resize().persistent(true);
}

/** Розбиває кнопки на рядки по N. */
export function chunk<T>(items: T[], size: number): T[][] {
  const rows: T[][] = [];
  for (let i = 0; i < items.length; i += size) rows.push(items.slice(i, i + size));
  return rows;
}

export function inline(rows: InlineKeyboardButton[][]) {
  return Markup.inlineKeyboard(rows);
}

export const btn = Markup.button;

import type { InlineKeyboardButton } from "telegraf/types";
import type { BoxState, Completeness, ProductCondition } from "../generated/prisma/client.js";
import { cb } from "../bot/callbackData.js";
import type { BotContext } from "../bot/context.js";
import { btn, chunk } from "../bot/keyboards.js";
import { reply } from "../bot/ui.js";
import { BOX_LABELS, COMPLETENESS_LABELS, CONDITION_LABELS, productTitle } from "../catalog/productPresenter.js";
import { THEME_SUGGESTIONS } from "../catalog/themes.js";
import { escapeHtml, formatMoney, truncate } from "../lib/format.js";
import {
  parseNonNegativeInt,
  parsePositiveInt,
  parsePrice,
  validateImageUrl,
  validateLongText,
  validateProductName,
  validateSetNumber,
  validateTheme,
} from "../lib/validation.js";
import { productAdminView } from "./adminViews.js";

export const WIZARD_SCENE = "np";

type WizardStep =
  | "name"
  | "set"
  | "theme"
  | "pieces"
  | "age"
  | "cond"
  | "box"
  | "comp"
  | "note"
  | "price"
  | "stock"
  | "photo"
  | "desc"
  | "confirm";

interface Draft {
  name?: string;
  setNumber?: string | null;
  theme?: string;
  pieces?: number | null;
  ageMin?: number | null;
  condition?: ProductCondition;
  boxState?: BoxState;
  completeness?: Completeness;
  conditionNote?: string | null;
  price?: string;
  stock?: number;
  imageUrl?: string | null;
  telegramFileId?: string | null;
  description?: string | null;
}

export interface WizardData {
  step: WizardStep;
  draft: Draft;
}

const ORDER: WizardStep[] = ["name", "set", "theme", "pieces", "age", "cond", "box", "comp", "note", "price", "stock", "photo", "desc", "confirm"];

function needsNote(d: Draft): boolean {
  return d.condition === "USED" || (d.boxState !== undefined && d.boxState !== "ORIGINAL") || (d.completeness !== undefined && d.completeness !== "COMPLETE");
}

function nextStep(current: WizardStep, d: Draft): WizardStep {
  let idx = ORDER.indexOf(current) + 1;
  while (idx < ORDER.length) {
    const step = ORDER[idx]!;
    if (step === "note" && !needsNote(d)) {
      idx += 1;
      continue;
    }
    return step;
  }
  return "confirm";
}

const skip = (step: WizardStep, label = "⏭ Пропустити") => btn.callback(label, cb.adminWizard(step, "skip"));
const cancelBtn = () => btn.callback("❌ Скасувати", cb.adminWizardCancel());

async function save(ctx: BotContext, data: WizardData): Promise<void> {
  await ctx.services.userState.set(BigInt(ctx.from!.id), WIZARD_SCENE, data);
}

export async function startProductWizard(ctx: BotContext): Promise<void> {
  const data: WizardData = { step: "name", draft: {} };
  await save(ctx, data);
  await promptWizard(ctx, data);
}

export async function promptWizard(ctx: BotContext, data: WizardData): Promise<void> {
  const d = data.draft;
  const title = "➕ <b>Новий набір LEGO</b>";
  const rows: InlineKeyboardButton[][] = [];
  let text = "";
  switch (data.step) {
    case "name":
      text = `${title}\n\nВведіть <b>назву набору</b> без тематики й номера, наприклад: <i>Bugatti Bolide</i>`;
      break;
    case "set":
      text = `${title}\n\nВведіть <b>офіційний номер набору</b> LEGO (наприклад: <i>42151</i>) або пропустіть, якщо він невідомий.`;
      rows.push([skip("set", "⏭ Номер невідомий")]);
      break;
    case "theme":
      text = `${title}\n\nОберіть <b>тематику</b> або напишіть свою:`;
      rows.push(...chunk(THEME_SUGGESTIONS.map((t, i) => btn.callback(t.replace("LEGO ", ""), cb.adminWizard("theme", String(i)))), 3));
      break;
    case "pieces":
      text = `${title}\n\nВведіть <b>кількість деталей</b> або пропустіть, якщо невідомо.`;
      rows.push([skip("pieces", "⏭ Невідомо")]);
      break;
    case "age":
      text = `${title}\n\nОберіть <b>рекомендований вік</b> (від скількох років) або введіть число:`;
      rows.push(...chunk([4, 6, 7, 8, 9, 10, 12, 14, 16, 18].map((a) => btn.callback(`${a}+`, cb.adminWizard("age", String(a)))), 5));
      rows.push([skip("age", "⏭ Невідомо")]);
      break;
    case "cond":
      text = `${title}\n\n<b>Стан</b> набору:`;
      rows.push([
        btn.callback("🆕 Новий", cb.adminWizard("cond", "NEW")),
        btn.callback("♻️ Вживаний", cb.adminWizard("cond", "USED")),
      ]);
      break;
    case "box":
      text = `${title}\n\n<b>Коробка</b>:`;
      rows.push([btn.callback("🎁 В оригінальній коробці", cb.adminWizard("box", "ORIGINAL"))]);
      rows.push([
        btn.callback("📦 Коробка пошкоджена", cb.adminWizard("box", "DAMAGED")),
        btn.callback("🚫 Без коробки", cb.adminWizard("box", "NONE")),
      ]);
      break;
    case "comp":
      text = `${title}\n\n<b>Комплектність</b>:`;
      rows.push([btn.callback("✅ Повний комплект", cb.adminWizard("comp", "COMPLETE"))]);
      rows.push([
        btn.callback("⚠️ Бракує деталей", cb.adminWizard("comp", "INCOMPLETE")),
        btn.callback("❔ Не перевірено", cb.adminWizard("comp", "UNCHECKED")),
      ]);
      break;
    case "note":
      text =
        d.completeness === "INCOMPLETE"
          ? `${title}\n\nОпишіть, <b>чого бракує</b> (обов’язково), наприклад: «немає 3 деталей і інструкції».`
          : `${title}\n\nДодайте <b>примітку щодо стану</b> (подряпини, стан коробки тощо) або пропустіть.`;
      if (d.completeness !== "INCOMPLETE") rows.push([skip("note")]);
      break;
    case "price":
      text = `${title}\n\nВведіть <b>ціну продажу</b> в гривнях, наприклад: <i>1800</i>`;
      break;
    case "stock":
      text = `${title}\n\nСкільки наборів <b>на складі</b>? Оберіть або введіть число:`;
      rows.push([1, 2, 3, 5, 10].map((n) => btn.callback(String(n), cb.adminWizard("stock", String(n)))));
      break;
    case "photo":
      text = `${title}\n\nНадішліть <b>фото</b> набору або посилання на зображення (https://…), чи пропустіть.`;
      rows.push([skip("photo", "⏭ Без фото")]);
      break;
    case "desc":
      text = `${title}\n\nДодайте короткий <b>опис</b> або пропустіть.`;
      rows.push([skip("desc")]);
      break;
    case "confirm": {
      text = [
        "🧾 <b>Перевірте новий набір</b>",
        "",
        `Назва: <b>${escapeHtml(productTitle({ theme: d.theme ?? "", setNumber: d.setNumber ?? null, name: d.name ?? "" }))}</b>`,
        `Номер набору: ${d.setNumber ? escapeHtml(d.setNumber) : "—"}`,
        `Тематика: ${escapeHtml(d.theme ?? "—")}`,
        `Деталей: ${d.pieces ?? "—"}`,
        `Вік: ${d.ageMin != null ? `${d.ageMin}+` : "—"}`,
        `Стан: ${d.condition ? CONDITION_LABELS[d.condition] : "—"}, ${d.boxState ? BOX_LABELS[d.boxState] : "—"}, ${
          d.completeness ? COMPLETENESS_LABELS[d.completeness] : "—"
        }`,
        `Примітка: ${d.conditionNote ? escapeHtml(d.conditionNote) : "—"}`,
        `Ціна: <b>${d.price ? formatMoney(d.price) : "—"}</b>`,
        `На складі: <b>${d.stock ?? 0}</b>`,
        `Фото: ${d.telegramFileId ? "так" : d.imageUrl ? escapeHtml(truncate(d.imageUrl, 50)) : "немає"}`,
        `Опис: ${d.description ? escapeHtml(truncate(d.description, 200)) : "—"}`,
      ].join("\n");
      rows.push([btn.callback("✅ Зберегти", cb.adminWizardSave())]);
      rows.push([btn.callback("🔄 Почати заново", cb.adminWizardRestart()), cancelBtn()]);
      await reply(ctx, text, { inline_keyboard: rows });
      return;
    }
  }
  rows.push([cancelBtn()]);
  await reply(ctx, text, { inline_keyboard: rows });
}

async function advance(ctx: BotContext, data: WizardData, patch: Draft): Promise<void> {
  const draft = { ...data.draft, ...patch };
  const next: WizardData = { step: nextStep(data.step, draft), draft };
  await save(ctx, next);
  await promptWizard(ctx, next);
}

async function invalid(ctx: BotContext, error: string): Promise<void> {
  await reply(ctx, `⚠️ ${escapeHtml(error)}`, { inline_keyboard: [[cancelBtn()]] });
}

export async function handleWizardText(ctx: BotContext, data: WizardData, text: string): Promise<void> {
  switch (data.step) {
    case "name": {
      const r = validateProductName(text);
      return r.ok ? advance(ctx, data, { name: r.value }) : invalid(ctx, r.error);
    }
    case "set": {
      const r = validateSetNumber(text);
      if (!r.ok) return invalid(ctx, r.error);
      const existing = await ctx.services.products.findBySetNumber(r.value, { includeArchived: true });
      if (existing.length > 0) {
        await reply(
          ctx,
          `ℹ️ У каталозі вже є товар з номером ${escapeHtml(r.value)}: ${existing
            .map((p) => `#${p.id} (${CONDITION_LABELS[p.condition]}, на складі ${p.stockOnHand})`)
            .join(", ")}.\nЯкщо це той самий товар у тому ж стані — краще поповнити залишок через /addstock. Продовжую створення нової позиції.`,
        );
      }
      return advance(ctx, data, { setNumber: r.value });
    }
    case "theme": {
      const r = validateTheme(text);
      return r.ok ? advance(ctx, data, { theme: r.value }) : invalid(ctx, r.error);
    }
    case "pieces": {
      const r = parsePositiveInt(text, 100_000);
      return r.ok ? advance(ctx, data, { pieces: r.value }) : invalid(ctx, r.error);
    }
    case "age": {
      const r = parseNonNegativeInt(text.replace("+", ""), 99);
      return r.ok ? advance(ctx, data, { ageMin: r.value }) : invalid(ctx, r.error);
    }
    case "note": {
      const r = validateLongText(text, 500);
      return r.ok ? advance(ctx, data, { conditionNote: r.value }) : invalid(ctx, r.error);
    }
    case "price": {
      const r = parsePrice(text);
      return r.ok ? advance(ctx, data, { price: r.value }) : invalid(ctx, r.error);
    }
    case "stock": {
      const r = parseNonNegativeInt(text, 100_000);
      return r.ok ? advance(ctx, data, { stock: r.value }) : invalid(ctx, r.error);
    }
    case "photo": {
      const r = validateImageUrl(text);
      return r.ok ? advance(ctx, data, { imageUrl: r.value, telegramFileId: null }) : invalid(ctx, r.error);
    }
    case "desc": {
      const r = validateLongText(text, 2000);
      return r.ok ? advance(ctx, data, { description: r.value }) : invalid(ctx, r.error);
    }
    case "cond":
    case "box":
    case "comp":
      await reply(ctx, "Оберіть, будь ласка, варіант кнопкою нижче 👇");
      return promptWizard(ctx, data);
    case "confirm":
      await reply(ctx, "Натисніть «✅ Зберегти» або «❌ Скасувати».");
      return;
  }
}

export async function handleWizardPhoto(ctx: BotContext, data: WizardData, fileId: string): Promise<void> {
  if (data.step !== "photo") {
    await reply(ctx, "Фото можна додати на кроці «Фото». Продовжуйте, будь ласка, поточний крок.");
    return;
  }
  await advance(ctx, data, { telegramFileId: fileId, imageUrl: null });
}

export async function handleWizardButton(ctx: BotContext, data: WizardData, step: string, value: string): Promise<void> {
  if (step !== data.step) {
    await reply(ctx, "Ця кнопка вже неактуальна — продовжуйте з поточного кроку.");
    return promptWizard(ctx, data);
  }
  switch (data.step) {
    case "set":
      return advance(ctx, data, { setNumber: null });
    case "theme": {
      const theme = THEME_SUGGESTIONS[Number(value)];
      return theme ? advance(ctx, data, { theme }) : promptWizard(ctx, data);
    }
    case "pieces":
      return advance(ctx, data, { pieces: null });
    case "age":
      return advance(ctx, data, { ageMin: value === "skip" ? null : Number(value) });
    case "cond":
      if (value === "NEW" || value === "USED") return advance(ctx, data, { condition: value });
      return promptWizard(ctx, data);
    case "box":
      if (value === "ORIGINAL" || value === "DAMAGED" || value === "NONE") return advance(ctx, data, { boxState: value });
      return promptWizard(ctx, data);
    case "comp":
      if (value === "COMPLETE" || value === "INCOMPLETE" || value === "UNCHECKED") {
        return advance(ctx, data, { completeness: value, conditionNote: null });
      }
      return promptWizard(ctx, data);
    case "note":
      return advance(ctx, data, { conditionNote: null });
    case "stock":
      return advance(ctx, data, { stock: Number(value) });
    case "photo":
      return advance(ctx, data, { imageUrl: null, telegramFileId: null });
    case "desc":
      return advance(ctx, data, { description: null });
    default:
      return promptWizard(ctx, data);
  }
}

export async function saveWizard(ctx: BotContext, data: WizardData): Promise<void> {
  const d = data.draft;
  if (data.step !== "confirm" || !d.name || !d.theme || !d.price || d.stock === undefined || !d.condition || !d.boxState || !d.completeness) {
    await reply(ctx, "Не всі дані заповнено. Продовжуйте, будь ласка, майстер.");
    return promptWizard(ctx, data);
  }
  const product = await ctx.services.products.create(
    {
      name: d.name,
      setNumber: d.setNumber ?? null,
      theme: d.theme,
      pieces: d.pieces ?? null,
      ageMin: d.ageMin ?? null,
      price: d.price,
      stock: d.stock,
      condition: d.condition,
      boxState: d.boxState,
      completeness: d.completeness,
      conditionNote: d.conditionNote ?? null,
      imageUrl: d.imageUrl ?? null,
      telegramFileId: d.telegramFileId ?? null,
      description: d.description ?? null,
    },
    BigInt(ctx.from!.id),
  );
  await ctx.services.userState.clear(BigInt(ctx.from!.id));
  await reply(ctx, `✅ Набір додано до каталогу (код товару <code>#${product.id}</code>).`);
  const view = productAdminView(product);
  await reply(ctx, view.text, view.markup);
}

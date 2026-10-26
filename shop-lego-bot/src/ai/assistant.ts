import Anthropic from "@anthropic-ai/sdk";
import { betaZodTool } from "@anthropic-ai/sdk/helpers/beta/zod";
import { z } from "zod";
import type { ChatMessage, Customer } from "../generated/prisma/client.js";
import type { AppConfig } from "../config/env.js";
import { BOX_LABELS, COMPLETENESS_LABELS, CONDITION_LABELS, productTitle } from "../catalog/productPresenter.js";
import type { ProductService, ProductView } from "../catalog/productService.js";
import type { PurchasedSet } from "../customers/customerService.js";
import { formatDate } from "../lib/format.js";
import { logger } from "../lib/logger.js";
import { ORDER_STATUS_LABELS, PAYMENT_METHOD_LABELS } from "../orders/orderStatus.js";
import type { OrderService } from "../orders/orderService.js";
import { NumberWhitelist, findUnverifiedNumbers } from "./guard.js";
import { SAFE_LEAD_IN, buildSystemPrompt } from "./prompt.js";

export interface AssistantInput {
  customer: Customer;
  text: string;
  history: ChatMessage[];
  lastShown: ProductView[];
  purchased: PurchasedSet[];
  activeCheckoutTitle: string | null;
}

export interface AssistantReply {
  /** Текст відповіді (простий текст, ще не екранований для HTML). */
  text: string | null;
  /** Товари, картки яких бот покаже під відповіддю (дані беруться з БД). */
  showProductIds: number[];
  /** Почати оформлення замовлення після відповіді. */
  startCheckout: { productId: number; quantity: number | null } | null;
  /** Текст моделі відхилено перевіркою чисел. */
  guardTriggered: boolean;
}

class TurnState {
  readonly whitelist = new NumberWhitelist();
  showIds: number[] = [];
  checkout: { productId: number; quantity: number | null } | null = null;
}

/** Обмеження JSON Schema, які не підтримує strict-режим інструментів, переносимо в опис. */
const UNSUPPORTED_KEYS = new Set([
  "$schema",
  "minimum",
  "maximum",
  "exclusiveMinimum",
  "exclusiveMaximum",
  "multipleOf",
  "minLength",
  "maxLength",
  "pattern",
  "maxItems",
  "uniqueItems",
]);

function sanitizeSchema(schema: unknown): unknown {
  if (Array.isArray(schema)) return schema.map(sanitizeSchema);
  if (!schema || typeof schema !== "object") return schema;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(schema as Record<string, unknown>)) {
    if (UNSUPPORTED_KEYS.has(key)) continue;
    if (key === "minItems" && typeof value === "number" && value > 1) continue;
    out[key] = sanitizeSchema(value);
  }
  return out;
}

function strictTool<S extends z.ZodObject>(options: {
  name: string;
  description: string;
  inputSchema: S;
  run: (input: z.infer<S>) => Promise<string>;
}) {
  const tool = betaZodTool({ ...options, strict: true });
  if (!("input_schema" in tool)) return tool;
  return { ...tool, input_schema: sanitizeSchema(tool.input_schema) } as typeof tool;
}

function toolProduct(p: ProductView) {
  return {
    id: p.id,
    title: productTitle(p),
    name: p.name,
    set_number: p.setNumber,
    theme: p.theme,
    price_uah: Number(p.price),
    available_qty: p.available,
    availability:
      p.availability === "IN_STOCK" ? "в наявності" : p.availability === "LOW_STOCK" ? "залишилося мало" : "немає в наявності",
    condition: CONDITION_LABELS[p.condition],
    box: BOX_LABELS[p.boxState],
    completeness: COMPLETENESS_LABELS[p.completeness],
    condition_note: p.conditionNote,
    pieces: p.pieces,
    age_min: p.ageMin,
  };
}

/** Прибирає Markdown, який Telegram у режимі HTML показав би як є. */
export function sanitizeModelText(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/gs, "$1")
    .replace(/__(.+?)__/gs, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, "$1 ($2)")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .slice(0, 1500);
}

/** Користувацький текст у тегах: кутові дужки замінюємо, щоб не можна було «закрити» тег. */
function neutralize(text: string): string {
  return text.replace(/</g, "‹").replace(/>/g, "›");
}

/**
 * Консультант на базі Claude. Модель лише розуміє запит і викликає інструменти
 * читання каталогу; ціни й наявність у картках формує код із БД, а оформлення
 * замовлення та зміни складу виконує програмна логіка з транзакціями.
 */
export class ShopAssistant {
  private readonly systemPrompt: string;

  constructor(
    private readonly client: Anthropic,
    private readonly deps: { products: ProductService; orders: OrderService },
    private readonly config: AppConfig,
  ) {
    this.systemPrompt = buildSystemPrompt(config.shop.name);
  }

  static createClient(config: AppConfig): Anthropic {
    return new Anthropic({ apiKey: config.ai.apiKey, timeout: config.ai.timeoutMs, maxRetries: 2 });
  }

  private buildTools(customerId: number, state: TurnState) {
    const { products, orders } = this.deps;
    const shop = this.config.shop;
    const remember = (json: string) => {
      state.whitelist.addText(json);
      return json;
    };

    return [
      strictTool({
        name: "search_products",
        description:
          "Пошук наборів LEGO в каталозі магазину. Викликай для будь-якого питання про асортимент, наявність, ціни, тематики, бюджет чи вік. Повертає лише реальні товари з бази з актуальними цінами й залишками.",
        inputSchema: z.object({
          query: z
            .string()
            .nullable()
            .describe("Ключові слова з назви моделі, напр. «Bugatti», «Millennium Falcon» (без слів «LEGO», «набір»); null — без текстового пошуку"),
          theme: z
            .string()
            .nullable()
            .describe("Тематика (серія), напр. «LEGO Technic», «LEGO Star Wars», «LEGO City»; null — будь-яка"),
          set_number: z
            .string()
            .nullable()
            .describe("Номер набору, лише якщо покупець сам його назвав, напр. «42151»; інакше null"),
          min_price: z.number().nullable().describe("Мінімальна ціна в гривнях або null"),
          max_price: z.number().nullable().describe("Максимальна ціна в гривнях («до 2000 грн» → 2000) або null"),
          child_age: z
            .number()
            .int()
            .min(0)
            .max(99)
            .nullable()
            .describe("Вік дитини в роках: повертаються набори з рекомендованим віком не старше; null — без фільтра"),
          condition: z.enum(["new", "used"]).nullable().describe("new — нові, used — вживані, null — будь-які"),
          include_out_of_stock: z
            .boolean()
            .describe("true — включити товари з нульовим залишком (щоб точно сказати, що конкретного набору немає); зазвичай false"),
          sort: z
            .enum(["relevance", "price_asc", "price_desc", "newest"])
            .describe("relevance — за відповідністю, price_asc — від дешевших, price_desc — від дорожчих, newest — новинки"),
          limit: z.number().int().min(1).max(10).describe("Скільки товарів повернути: від 1 до 10, зазвичай 5"),
        }),
        run: async (input) => {
          const result = await products.search({
            text: input.query,
            theme: input.theme,
            setNumber: input.set_number,
            minPrice: input.min_price,
            maxPrice: input.max_price,
            childAge: input.child_age,
            condition: input.condition === "new" ? "NEW" : input.condition === "used" ? "USED" : null,
            onlyAvailable: !input.include_out_of_stock,
            sort: input.sort,
            limit: input.limit,
          });
          return remember(
            JSON.stringify({
              total_found: result.total,
              products: result.items.map(toolProduct),
              ...(result.total === 0 ? { note: "У каталозі магазину нічого не знайдено за цими умовами." } : {}),
            }),
          );
        },
      }),
      strictTool({
        name: "get_product_details",
        description:
          "Повна інформація про товар за його id з результатів пошуку: ціна, наявність, стан, комплектність, опис. Викликай, коли покупець питає про конкретний набір («цей», «скільки коштує», «чи є в наявності»).",
        inputSchema: z.object({ product_id: z.number().int().describe("id товару з результатів інструментів або контексту") }),
        run: async ({ product_id }) => {
          const p = await products.getById(product_id);
          if (!p || p.status !== "ACTIVE") {
            return remember(JSON.stringify({ error: "Товар не знайдено в каталозі магазину" }));
          }
          return remember(
            JSON.stringify({
              ...toolProduct(p),
              description: p.description ? p.description.slice(0, 1000) : null,
              has_photo: Boolean(p.telegramFileId || p.imageUrl),
            }),
          );
        },
      }),
      strictTool({
        name: "list_themes",
        description: "Список тематик (серій) LEGO, які зараз є в магазині, з кількістю доступних наборів і мінімальною ціною.",
        inputSchema: z.object({}),
        run: async () => {
          const themes = await products.listThemes();
          return remember(
            JSON.stringify({
              themes: themes
                .filter((t) => t.availableCount > 0)
                .map((t) => ({ theme: t.theme, available_products: t.availableCount, min_price_uah: t.minPrice })),
            }),
          );
        },
      }),
      strictTool({
        name: "get_my_orders",
        description:
          "Замовлення поточного покупця (останні 10): номер, дата, статус, товари, сума. Викликай, коли покупець питає про свої замовлення чи попередні покупки.",
        inputSchema: z.object({}),
        run: async () => {
          const list = await orders.customerOrders(customerId, 10);
          return remember(
            JSON.stringify({
              orders: list.map((o) => ({
                order_number: o.id,
                date: formatDate(o.createdAt, shop.timezone),
                status: ORDER_STATUS_LABELS[o.status],
                items: o.items.map((i) => ({
                  title: productTitle({ theme: i.theme, setNumber: i.setNumber, name: i.productName }),
                  product_id: i.productId,
                  quantity: i.quantity,
                  unit_price_uah: Number(i.unitPrice),
                })),
                total_uah: Number(o.totalAmount),
              })),
            }),
          );
        },
      }),
      strictTool({
        name: "get_shop_info",
        description: "Умови доставки, оплати, графік роботи й контакти магазину.",
        inputSchema: z.object({}),
        run: async () =>
          remember(
            JSON.stringify({
              shop_name: shop.name,
              contact: shop.contact ?? null,
              working_hours: shop.workingHours,
              delivery: shop.deliveryInfo,
              payment: shop.paymentInfo,
              payment_methods: shop.paymentMethods.map((m) => PAYMENT_METHOD_LABELS[m]),
            }),
          ),
      }),
      strictTool({
        name: "show_products",
        description:
          "Показати покупцю картки товарів (до 8) під твоєю відповіддю. Бот сам виведе перевірені назви, ціни, наявність і кнопки замовлення.",
        inputSchema: z.object({
          product_ids: z.array(z.number().int()).describe("id товарів з результатів інструментів, у порядку показу (до 8)"),
        }),
        run: async ({ product_ids }) => {
          const unique = [...new Set(product_ids)].slice(0, 8);
          const found = (await products.getMany(unique)).filter((p) => p.status === "ACTIVE");
          state.showIds = found.map((p) => p.id);
          const missing = unique.filter((id) => !state.showIds.includes(id));
          return JSON.stringify({
            shown_ids: state.showIds,
            not_found_ids: missing,
            note: "Картки з перевіреними цінами й наявністю буде показано під твоєю відповіддю — не перелічуй їх у тексті.",
          });
        },
      }),
      strictTool({
        name: "start_checkout",
        description:
          "Почати оформлення замовлення конкретного набору, коли покупець чітко хоче його купити. Бот сам запитає контакти, доставку й оплату та покаже підсумок для підтвердження.",
        inputSchema: z.object({
          product_id: z.number().int().describe("id товару"),
          quantity: z.number().int().min(1).max(100).nullable().describe("Кількість, якщо покупець її назвав, інакше null"),
        }),
        run: async ({ product_id, quantity }) => {
          const p = await products.getById(product_id);
          if (!p || p.status !== "ACTIVE") return JSON.stringify({ ok: false, reason: "Товар не знайдено в каталозі" });
          if (p.available === 0) return remember(JSON.stringify({ ok: false, reason: "Товару немає в наявності", available_qty: 0 }));
          if (quantity !== null && quantity > p.available) {
            return remember(
              JSON.stringify({ ok: false, reason: `Доступно лише ${p.available} шт.`, available_qty: p.available }),
            );
          }
          state.checkout = { productId: p.id, quantity };
          return remember(
            JSON.stringify({
              ok: true,
              note: "Після твоєї відповіді бот почне оформлення. Напиши коротке підтвердження без запитань про контакти.",
              title: productTitle(p),
            }),
          );
        },
      }),
    ];
  }

  private buildUserContent(input: AssistantInput): string {
    const context: string[] = [];
    context.push(`Ім'я покупця в Telegram: ${input.customer.firstName ?? "невідоме"}`);
    if (input.purchased.length > 0) {
      context.push(
        `Раніше покупець замовляв: ${input.purchased
          .slice(0, 5)
          .map((p) => `${p.title} (product_id=${p.productId}, замовлення №${p.lastOrderId})`)
          .join("; ")}`,
      );
    } else {
      context.push("Покупець ще нічого не замовляв у магазині.");
    }
    if (input.lastShown.length > 0) {
      context.push(
        `Товари, які бот показав покупцю останніми: ${input.lastShown
          .slice(0, 8)
          .map((p) => `${productTitle(p)} (product_id=${p.id})`)
          .join("; ")}`,
      );
    }
    if (input.activeCheckoutTitle) {
      context.push(`У покупця є незавершене оформлення замовлення: ${input.activeCheckoutTitle}.`);
    }
    const history = input.history
      .map((m) => `${m.role === "USER" ? "Покупець" : "Консультант"}: ${m.text}`)
      .join("\n");
    const text = input.text.slice(0, this.config.ai.maxMessageLength);
    return [
      `<context>\n${neutralize(context.join("\n"))}\n</context>`,
      history ? `<history>\n${neutralize(history)}\n</history>` : "",
      `<customer_message>\n${neutralize(text)}\n</customer_message>`,
    ]
      .filter(Boolean)
      .join("\n\n");
  }

  async respond(input: AssistantInput): Promise<AssistantReply | null> {
    const state = new TurnState();
    const userContent = this.buildUserContent(input);
    state.whitelist.addText(userContent);
    const shop = this.config.shop;
    for (const t of [shop.contact, shop.workingHours, shop.deliveryInfo, shop.paymentInfo]) state.whitelist.addText(t);

    const ai = this.config.ai;
    const runner = this.client.beta.messages.toolRunner({
      model: ai.model,
      max_tokens: ai.maxTokens,
      system: [{ type: "text", text: this.systemPrompt, cache_control: { type: "ephemeral" } }],
      tools: this.buildTools(input.customer.id, state),
      messages: [{ role: "user", content: userContent }],
      output_config: { effort: ai.effort },
      max_iterations: ai.maxIterations,
      thread: false,
      ...(ai.serverFallbacks ? { betas: ["server-side-fallback-2026-07-01"], fallbacks: "default" as const } : {}),
    });
    const final = await runner.runUntilDone();

    if (final.stop_reason === "refusal") {
      logger.warn({ category: final.stop_details?.category ?? null }, "Claude відхилив запит (refusal)");
      return null;
    }
    const complete = final.stop_reason === "end_turn" || final.stop_reason === "stop_sequence";
    const rawText = final.content
      .filter((b): b is Anthropic.Beta.BetaTextBlock => b.type === "text")
      .map((b) => b.text)
      .join("\n\n");
    let text: string | null = complete ? sanitizeModelText(rawText) : null;
    let guardTriggered = false;

    if (text) {
      const unverified = findUnverifiedNumbers(text, state.whitelist);
      if (unverified.length > 0) {
        guardTriggered = true;
        logger.warn({ unverified, customerId: input.customer.id }, "Відповідь Claude містить неперевірені числа — замінено");
        text = null;
      }
    }
    if (!text) {
      if (state.showIds.length > 0) text = SAFE_LEAD_IN;
      else if (state.checkout) text = "Добре, оформлюємо замовлення 👍";
      else return null;
    }
    logger.debug(
      {
        stop: final.stop_reason,
        usage: {
          input: final.usage.input_tokens,
          output: final.usage.output_tokens,
          cacheRead: final.usage.cache_read_input_tokens,
        },
      },
      "Відповідь Claude",
    );
    return { text, showProductIds: state.showIds, startCheckout: state.checkout, guardTriggered };
  }
}

import { z } from "zod";

/** Усі налаштування беруться зі змінних середовища (.env) і перевіряються під час запуску. */

const bool = z
  .enum(["true", "false", "1", "0", "yes", "no", "TRUE", "FALSE"])
  .transform((v) => ["true", "1", "yes", "TRUE"].includes(v));

const optionalString = z
  .string()
  .optional()
  .transform((v) => (v && v.trim() !== "" ? v.trim() : undefined));

/** Дозволяє писати переноси рядків у .env як \n. */
const multiline = (fallback: string) =>
  z
    .string()
    .optional()
    .transform((v) => (v && v.trim() !== "" ? v.replace(/\\n/g, "\n").trim() : fallback));

const PAYMENT_METHOD_VALUES = ["CASH_ON_DELIVERY", "CARD_TRANSFER", "BANK_TRANSFER"] as const;
export type PaymentMethodCode = (typeof PAYMENT_METHOD_VALUES)[number];

const EnvSchema = z.object({
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),

  // Telegram
  BOT_TOKEN: z
    .string({ error: "BOT_TOKEN не задано — отримайте токен у @BotFather" })
    .trim()
    .regex(/^\d+:[A-Za-z0-9_-]{20,}$/, "BOT_TOKEN має формат 123456789:AA..."),
  ADMIN_IDS: z
    .string({ error: "ADMIN_IDS не задано — вкажіть Telegram ID власника" })
    .trim()
    .min(1, "ADMIN_IDS не може бути порожнім")
    .transform((v, ctx) => {
      const ids = v
        .split(/[,\s;]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const parsed: bigint[] = [];
      for (const id of ids) {
        if (!/^\d{3,20}$/.test(id)) {
          ctx.addIssue({ code: "custom", message: `Некоректний Telegram ID у ADMIN_IDS: ${id}` });
          return z.NEVER;
        }
        parsed.push(BigInt(id));
      }
      return parsed;
    }),

  // База даних
  DATABASE_URL: z
    .string({ error: "DATABASE_URL не задано" })
    .trim()
    .regex(/^postgres(ql)?:\/\//, "DATABASE_URL має починатися з postgresql://"),
  DATABASE_POOL_SIZE: z.coerce.number().int().min(1).max(100).default(10),

  // Claude API
  ANTHROPIC_API_KEY: optionalString,
  AI_ENABLED: bool.default(true),
  CLAUDE_MODEL: z.string().trim().min(1).default("claude-opus-5-5"),
  CLAUDE_EFFORT: z.enum(["low", "medium", "high", "xhigh", "max"]).default("low"),
  CLAUDE_MAX_TOKENS: z.coerce.number().int().min(1024).max(20000).default(16000),
  CLAUDE_TIMEOUT_MS: z.coerce.number().int().min(5000).max(600000).default(90000),
  CLAUDE_MAX_ITERATIONS: z.coerce.number().int().min(2).max(10).default(5),
  CLAUDE_SERVER_FALLBACKS: bool.default(true),
  AI_MAX_REQUESTS_PER_MINUTE: z.coerce.number().int().min(1).default(8),
  AI_MAX_REQUESTS_PER_DAY: z.coerce.number().int().min(1).default(200),
  AI_MAX_CONCURRENCY: z.coerce.number().int().min(1).max(50).default(4),
  AI_MAX_MESSAGE_LENGTH: z.coerce.number().int().min(50).max(4000).default(1000),

  // Магазин
  SHOP_NAME: z.string().trim().min(1).default("LEGO Shop"),
  SHOP_CONTACT: optionalString,
  SHOP_WORKING_HOURS: multiline("Приймаємо замовлення в боті цілодобово. Менеджер відповідає щодня з 9:00 до 20:00."),
  SHOP_DELIVERY_INFO: multiline(
    "Відправляємо Новою поштою та Укрпоштою по всій Україні. Вартість доставки — за тарифами перевізника.",
  ),
  SHOP_PAYMENT_INFO: multiline(
    "Можна оплатити при отриманні (накладений платіж) або переказом на картку після підтвердження замовлення.",
  ),
  PAYMENT_METHODS: z
    .string()
    .default("CASH_ON_DELIVERY,CARD_TRANSFER")
    .transform((v, ctx) => {
      const items = v
        .split(/[,\s;]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      const result: PaymentMethodCode[] = [];
      for (const item of items) {
        if (!(PAYMENT_METHOD_VALUES as readonly string[]).includes(item)) {
          ctx.addIssue({
            code: "custom",
            message: `Невідомий спосіб оплати ${item}. Допустимі: ${PAYMENT_METHOD_VALUES.join(", ")}`,
          });
          return z.NEVER;
        }
        if (!result.includes(item as PaymentMethodCode)) result.push(item as PaymentMethodCode);
      }
      if (result.length === 0) {
        ctx.addIssue({ code: "custom", message: "PAYMENT_METHODS має містити хоча б один спосіб оплати" });
        return z.NEVER;
      }
      return result;
    }),
  PAYMENT_DETAILS: multiline(""),
  DELIVERY_HINT: multiline(
    "Вкажіть номер відділення чи поштомату Нової пошти (наприклад: «Відділення №12») або адресу відділення Укрпошти з індексом.",
  ),
  MAX_QUANTITY_PER_ORDER: z.coerce.number().int().min(1).max(100).default(10),
  DEFAULT_LOW_STOCK_THRESHOLD: z.coerce.number().int().min(0).max(1000).default(2),
  TIMEZONE: z.string().default("Europe/Kyiv"),

  // Зберігання даних
  CHAT_HISTORY_RETENTION_DAYS: z.coerce.number().int().min(1).max(365).default(30),
  CHECKOUT_TTL_HOURS: z.coerce.number().int().min(1).max(24 * 30).default(72),

  // Логи
  LOG_LEVEL: z.enum(["fatal", "error", "warn", "info", "debug", "trace", "silent"]).default("info"),

  /** Власний сервер Telegram Bot API (необов'язково), напр. http://localhost:8081 */
  TELEGRAM_API_ROOT: optionalString,

  // Режим роботи: long polling (за замовчуванням) або webhook
  WEBHOOK_DOMAIN: optionalString,
  WEBHOOK_PATH: z.string().default("/telegram/webhook"),
  WEBHOOK_PORT: z.coerce.number().int().min(1).max(65535).default(8443),
  WEBHOOK_SECRET_TOKEN: optionalString.refine((v) => v === undefined || /^[A-Za-z0-9_-]{16,256}$/.test(v), {
    message: "WEBHOOK_SECRET_TOKEN: 16–256 символів A-Z, a-z, 0-9, _ або -",
  }),
  HEALTH_PORT: z.preprocess((v) => (v === "" ? undefined : v), z.coerce.number().int().min(1).max(65535).optional()),

  BROADCAST_MESSAGES_PER_SECOND: z.coerce.number().min(1).max(30).default(20),
});

export type AppConfig = ReturnType<typeof loadConfig>;

export function loadConfig(source: NodeJS.ProcessEnv = process.env) {
  const parsed = EnvSchema.safeParse(source);
  if (!parsed.success) {
    const details = parsed.error.issues.map((i) => `  • ${i.path.join(".") || "env"}: ${i.message}`).join("\n");
    throw new Error(`Помилка налаштувань (.env):\n${details}`);
  }
  const env = parsed.data;
  const aiEnabled = env.AI_ENABLED && Boolean(env.ANTHROPIC_API_KEY);
  return {
    nodeEnv: env.NODE_ENV,
    isProduction: env.NODE_ENV === "production",
    telegram: {
      token: env.BOT_TOKEN,
      adminIds: env.ADMIN_IDS,
      apiRoot: env.TELEGRAM_API_ROOT,
      webhook: env.WEBHOOK_DOMAIN
        ? {
            domain: env.WEBHOOK_DOMAIN,
            path: env.WEBHOOK_PATH,
            port: env.WEBHOOK_PORT,
            secretToken: env.WEBHOOK_SECRET_TOKEN,
          }
        : undefined,
    },
    database: { url: env.DATABASE_URL, poolSize: env.DATABASE_POOL_SIZE },
    ai: {
      enabled: aiEnabled,
      apiKey: env.ANTHROPIC_API_KEY,
      model: env.CLAUDE_MODEL,
      effort: env.CLAUDE_EFFORT,
      maxTokens: env.CLAUDE_MAX_TOKENS,
      timeoutMs: env.CLAUDE_TIMEOUT_MS,
      maxIterations: env.CLAUDE_MAX_ITERATIONS,
      serverFallbacks: env.CLAUDE_SERVER_FALLBACKS,
      maxRequestsPerMinute: env.AI_MAX_REQUESTS_PER_MINUTE,
      maxRequestsPerDay: env.AI_MAX_REQUESTS_PER_DAY,
      maxConcurrency: env.AI_MAX_CONCURRENCY,
      maxMessageLength: env.AI_MAX_MESSAGE_LENGTH,
    },
    shop: {
      name: env.SHOP_NAME,
      contact: env.SHOP_CONTACT,
      workingHours: env.SHOP_WORKING_HOURS,
      deliveryInfo: env.SHOP_DELIVERY_INFO,
      paymentInfo: env.SHOP_PAYMENT_INFO,
      paymentMethods: env.PAYMENT_METHODS,
      paymentDetails: env.PAYMENT_DETAILS,
      deliveryHint: env.DELIVERY_HINT,
      maxQuantityPerOrder: env.MAX_QUANTITY_PER_ORDER,
      defaultLowStockThreshold: env.DEFAULT_LOW_STOCK_THRESHOLD,
      timezone: env.TIMEZONE,
    },
    retention: {
      chatHistoryDays: env.CHAT_HISTORY_RETENTION_DAYS,
      checkoutTtlHours: env.CHECKOUT_TTL_HOURS,
    },
    logLevel: env.LOG_LEVEL,
    healthPort: env.HEALTH_PORT,
    broadcastRatePerSecond: env.BROADCAST_MESSAGES_PER_SECOND,
  };
}

import { createRequire } from "node:module";
import { pino, type Logger } from "pino";

export type { Logger };

const require = createRequire(import.meta.url);

function prettyAvailable(): boolean {
  try {
    require.resolve("pino-pretty");
    return true;
  } catch {
    return false;
  }
}

/**
 * Помилки Telegraf містять поле `on.payload` — тіло запиту до Telegram (тексти повідомлень
 * з іменами, телефонами й адресами покупців). У журнал потрапляє лише назва методу.
 */
export function serializeError(err: unknown): unknown {
  if (!(err instanceof Error)) return err;
  const serialized = pino.stdSerializers.err(err) as unknown as Record<string, unknown>;
  const on = serialized.on as { method?: unknown } | undefined;
  if (on && typeof on === "object") serialized.on = { method: on.method };
  return serialized;
}

/**
 * Журнал у форматі JSON (stdout). Персональні дані покупців маскуються.
 * LOG_PRETTY=true вмикає читабельний формат для розробки (потрібен pino-pretty).
 */
function createLogger(): Logger {
  const isTest = process.env.NODE_ENV === "test";
  const level = process.env.LOG_LEVEL ?? (isTest ? "silent" : "info");
  const wantPretty = process.env.LOG_PRETTY === "true";
  const pretty = wantPretty && prettyAvailable();
  const instance = pino({
    level,
    base: { app: "shop-lego-bot" },
    timestamp: pino.stdTimeFunctions.isoTime,
    serializers: { err: serializeError },
    redact: {
      paths: [
        "phone",
        "*.phone",
        "fullName",
        "*.fullName",
        "deliveryPoint",
        "*.deliveryPoint",
        "apiKey",
        "*.apiKey",
        "token",
        "*.token",
      ],
      censor: "[приховано]",
    },
    ...(pretty
      ? {
          transport: {
            target: "pino-pretty",
            options: { translateTime: "SYS:standard", ignore: "pid,hostname,app" },
          },
        }
      : {}),
  });
  if (wantPretty && !pretty) {
    instance.warn("LOG_PRETTY=true, але pino-pretty не встановлено — використовується JSON-формат");
  }
  return instance;
}

export const logger: Logger = createLogger();

/** Маскує номер телефону для журналів і повідомлень адміністратору в загальних списках. */
export function maskPhone(phone: string | null | undefined): string {
  if (!phone) return "—";
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 6) return "***";
  return `${phone.startsWith("+") ? "+" : ""}${digits.slice(0, 3)}***${digits.slice(-2)}`;
}

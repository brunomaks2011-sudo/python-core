import { execSync } from "node:child_process";
import { loadConfig, type AppConfig } from "../../src/config/env.js";
import { Prisma, createPrismaClient, type PrismaClient } from "../../src/database/client.js";
import type { BoxState, Completeness, ProductCondition } from "../../src/generated/prisma/client.js";

/** Окрема тестова база — тести очищають у ній УСІ таблиці. */
export const TEST_DATABASE_URL =
  process.env.TEST_DATABASE_URL ?? "postgresql://lego:lego_dev_password@localhost:5432/lego_shop_test?schema=public";

if (!/test/i.test(new URL(TEST_DATABASE_URL).pathname)) {
  throw new Error("TEST_DATABASE_URL має вказувати на окрему тестову базу (назва має містити «test»)");
}

export const ADMIN_ID = 900000001;

export function migrateTestDb(): void {
  execSync("npx prisma migrate deploy", {
    env: { ...process.env, DATABASE_URL: TEST_DATABASE_URL },
    stdio: "pipe",
  });
}

export function testConfig(overrides: Record<string, string> = {}): AppConfig {
  return loadConfig({
    NODE_ENV: "test",
    BOT_TOKEN: "123456789:TESTtokenTESTtokenTESTtokenTEST",
    ADMIN_IDS: String(ADMIN_ID),
    DATABASE_URL: TEST_DATABASE_URL,
    AI_ENABLED: "false",
    SHOP_NAME: "Тестовий LEGO",
    SHOP_CONTACT: "@lego_manager",
    PAYMENT_METHODS: "CASH_ON_DELIVERY,CARD_TRANSFER",
    PAYMENT_DETAILS: "Картка 0000 0000 0000 0000, ФОП Тест",
    ...overrides,
  });
}

export function testPrisma(): PrismaClient {
  return createPrismaClient({ url: TEST_DATABASE_URL, poolSize: 20 });
}

export async function resetDb(prisma: PrismaClient): Promise<void> {
  await prisma.$executeRawUnsafe(
    `TRUNCATE TABLE stock_movements, product_changes, order_status_history, order_items, orders, checkouts,
      chat_messages, notifications, broadcasts, user_states, processed_updates, customers, products
     RESTART IDENTITY CASCADE`,
  );
  await prisma.$executeRawUnsafe(`ALTER SEQUENCE orders_id_seq RESTART WITH 101`);
}

export async function createProduct(
  prisma: PrismaClient,
  data: Partial<{
    name: string;
    setNumber: string | null;
    theme: string;
    pieces: number | null;
    ageMin: number | null;
    price: string;
    stock: number;
    condition: ProductCondition;
    boxState: BoxState;
    completeness: Completeness;
    imageUrl: string | null;
  }> = {},
) {
  return prisma.product.create({
    data: {
      name: data.name ?? "Bugatti Bolide",
      setNumber: data.setNumber === undefined ? "42151" : data.setNumber,
      theme: data.theme ?? "LEGO Technic",
      pieces: data.pieces === undefined ? 905 : data.pieces,
      ageMin: data.ageMin === undefined ? 9 : data.ageMin,
      price: new Prisma.Decimal(data.price ?? "1800"),
      stockOnHand: data.stock ?? 5,
      condition: data.condition ?? "NEW",
      boxState: data.boxState ?? "ORIGINAL",
      completeness: data.completeness ?? "COMPLETE",
      imageUrl: data.imageUrl ?? null,
    },
  });
}

/** Фейковий відправник для сервісів (без бота). */
export function fakeSender() {
  const sent: Array<{ chatId: string; text: string }> = [];
  return {
    sent,
    async sendMessage(chatId: number | string, text: string) {
      sent.push({ chatId: String(chatId), text });
      return {};
    },
    async sendPhoto(chatId: number | string, _photo: string, extra?: { caption?: string }) {
      sent.push({ chatId: String(chatId), text: extra?.caption ?? "" });
      return {};
    },
  };
}

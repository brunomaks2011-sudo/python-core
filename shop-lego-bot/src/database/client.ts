import { PrismaPg } from "@prisma/adapter-pg";
import { Prisma, PrismaClient } from "../generated/prisma/client.js";
import { logger } from "../lib/logger.js";

export { Prisma, PrismaClient };
export type Tx = Prisma.TransactionClient;
export type Db = PrismaClient | Tx;

export function createPrismaClient(options: { url: string; poolSize: number }): PrismaClient {
  const adapter = new PrismaPg(
    {
      connectionString: options.url,
      max: options.poolSize,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
      // Prisma зберігає дати в UTC; однаковий часовий пояс для NOW() у SQL-запитах.
      options: "-c timezone=UTC",
    },
    {
      onPoolError: (err) => logger.error({ err }, "Помилка пулу з'єднань PostgreSQL"),
    },
  );
  return new PrismaClient({ adapter });
}

/** Інтерактивна транзакція з розумними тайм-аутами. */
export function inTransaction<T>(prisma: PrismaClient, fn: (tx: Tx) => Promise<T>): Promise<T> {
  return prisma.$transaction(fn, { maxWait: 10_000, timeout: 20_000 });
}

export function isUniqueViolation(err: unknown): boolean {
  return err instanceof Prisma.PrismaClientKnownRequestError && err.code === "P2002";
}

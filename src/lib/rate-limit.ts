import { prisma } from "@/lib/prisma";

export type RateLimitResult = { ok: boolean; remaining: number; retryAfterSec: number };

/**
 * Лічильник спроб у фіксованому вікні, що зберігається в PostgreSQL.
 * Працює коректно і на кількох інстансах (Vercel, кілька контейнерів), бо стан у спільній БД.
 * Оновлення атомарне завдяки INSERT ... ON CONFLICT.
 */
export async function rateLimit(key: string, limit: number, windowMs: number): Promise<RateLimitResult> {
  const now = new Date();
  const reset = new Date(now.getTime() + windowMs);
  const rows = await prisma.$queryRaw<{ count: number; resetAt: Date }[]>`
    INSERT INTO "RateLimit" ("key", "count", "resetAt") VALUES (${key}, 1, ${reset})
    ON CONFLICT ("key") DO UPDATE SET
      "count"   = CASE WHEN "RateLimit"."resetAt" < ${now} THEN 1 ELSE "RateLimit"."count" + 1 END,
      "resetAt" = CASE WHEN "RateLimit"."resetAt" < ${now} THEN ${reset} ELSE "RateLimit"."resetAt" END
    RETURNING "count", "resetAt"`;
  const { count, resetAt } = rows[0];
  // Зрідка прибираємо прострочені записи
  if (Math.random() < 0.01) await prisma.rateLimit.deleteMany({ where: { resetAt: { lt: now } } }).catch(() => {});
  return {
    ok: count <= limit,
    remaining: Math.max(0, limit - count),
    retryAfterSec: Math.max(0, Math.ceil((new Date(resetAt).getTime() - now.getTime()) / 1000)),
  };
}

export async function resetRateLimit(key: string) {
  await prisma.rateLimit.delete({ where: { key } }).catch(() => {});
}

/** IP клієнта з заголовків reverse-proxy (Vercel / Caddy). */
export function clientIp(headers: Headers): string {
  const fwd = headers.get("x-forwarded-for");
  if (fwd) return fwd.split(",")[0].trim();
  return headers.get("x-real-ip") ?? "unknown";
}

/** Повертає одну спробу (наприклад, успішний вхід не має витрачати ліміт IP). */
export async function releaseRateLimit(key: string) {
  await prisma.rateLimit.updateMany({ where: { key, count: { gt: 0 } }, data: { count: { decrement: 1 } } }).catch(() => {});
}

import { logger } from "./logger.js";

/**
 * Послідовна обробка задач для одного ключа (наприклад, Telegram ID користувача):
 * оновлення одного покупця обробляються по черзі, різних покупців — паралельно.
 */
export class KeyedQueue {
  private readonly tails = new Map<string, Promise<void>>();
  private readonly inFlight = new Set<Promise<void>>();

  run(key: string, task: () => Promise<void>): Promise<void> {
    const previous = this.tails.get(key) ?? Promise.resolve();
    const current = previous
      .catch(() => undefined)
      .then(task)
      .catch((err) => logger.error({ err }, "Необроблена помилка в черзі оновлень"));
    const tail = current.finally(() => {
      if (this.tails.get(key) === tail) this.tails.delete(key);
      this.inFlight.delete(tail);
    });
    this.tails.set(key, tail);
    this.inFlight.add(tail);
    return current;
  }

  get size(): number {
    return this.inFlight.size;
  }

  /** Очікує завершення всіх задач (для коректної зупинки бота). */
  async drain(timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (this.inFlight.size > 0) {
      const remaining = deadline - Date.now();
      if (remaining <= 0) return false;
      await Promise.race([Promise.allSettled([...this.inFlight]), new Promise((r) => setTimeout(r, remaining))]);
    }
    return true;
  }
}

/** Обмеження кількості одночасних операцій (наприклад, запитів до Claude API). */
export class Semaphore {
  private active = 0;
  private readonly waiters: Array<() => void> = [];

  constructor(private readonly limit: number) {}

  async use<T>(fn: () => Promise<T>): Promise<T> {
    if (this.active >= this.limit) {
      await new Promise<void>((resolve) => this.waiters.push(resolve));
    }
    this.active += 1;
    try {
      return await fn();
    } finally {
      this.active -= 1;
      this.waiters.shift()?.();
    }
  }
}

/** Ліміт запитів на користувача: N за хвилину та M за добу (у пам'яті процесу). */
export class RateLimiter {
  private readonly minute = new Map<string, number[]>();
  private readonly day = new Map<string, { date: string; count: number }>();

  constructor(
    private readonly perMinute: number,
    private readonly perDay: number,
  ) {}

  tryAcquire(key: string, now = Date.now()): boolean {
    const recent = (this.minute.get(key) ?? []).filter((t) => now - t < 60_000);
    const today = new Date(now).toISOString().slice(0, 10);
    const daily = this.day.get(key);
    const dayCount = daily && daily.date === today ? daily.count : 0;
    if (recent.length >= this.perMinute || dayCount >= this.perDay) {
      this.minute.set(key, recent);
      return false;
    }
    recent.push(now);
    this.minute.set(key, recent);
    this.day.set(key, { date: today, count: dayCount + 1 });
    if (this.minute.size > 10_000) this.prune(now);
    return true;
  }

  private prune(now: number): void {
    for (const [key, times] of this.minute) {
      if (times.every((t) => now - t >= 60_000)) this.minute.delete(key);
    }
  }
}

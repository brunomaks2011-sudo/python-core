import { TelegramError } from "telegraf";
import type { InlineKeyboardMarkup } from "telegraf/types";
import type { Notification } from "../generated/prisma/client.js";
import { Prisma, type Db, type PrismaClient } from "../database/client.js";
import { errorMessage } from "../lib/errors.js";
import { logger } from "../lib/logger.js";

/** Мінімальний інтерфейс відправника — у продакшені це bot.telegram, у тестах — фейк. */
export interface MessageSender {
  sendMessage(
    chatId: number | string,
    text: string,
    extra?: {
      parse_mode?: "HTML";
      reply_markup?: InlineKeyboardMarkup;
      link_preview_options?: { is_disabled?: boolean };
    },
  ): Promise<unknown>;
}

export interface NotificationInput {
  kind: string;
  chatId: bigint;
  text: string;
  replyMarkup?: InlineKeyboardMarkup | null;
  dedupKey?: string | null;
  orderId?: number | null;
}

export interface NotificationHooks {
  /** Викликається після успішної доставки (наприклад, NEW → «очікує підтвердження»). */
  onSent?: (notification: Notification) => Promise<void>;
  /** Отримувач заблокував бота або чат недоступний. */
  onUnreachable?: (chatId: bigint) => Promise<void>;
}

const MAX_ATTEMPTS = 8;
const LEASE_SECONDS = 120;

export function isUnreachableError(err: unknown): boolean {
  if (!(err instanceof TelegramError)) return false;
  if (err.code === 403) return true;
  return err.code === 400 && /chat not found|user is deactivated|bot was blocked/i.test(err.description);
}

export function retryAfterSeconds(err: unknown): number | null {
  if (err instanceof TelegramError && err.code === 429) {
    return err.parameters?.retry_after ?? 5;
  }
  return null;
}

/**
 * Черга вихідних повідомлень (outbox). Записи створюються в тій самій транзакції,
 * що й замовлення, а надсилаються окремим обробником із повторними спробами.
 * Рядки «орендуються» через FOR UPDATE SKIP LOCKED, тож навіть два екземпляри
 * бота не надішлють одне повідомлення двічі.
 */
export class NotificationService {
  private timer: NodeJS.Timeout | null = null;
  private running: Promise<void> | null = null;
  private hooks: NotificationHooks = {};

  constructor(
    private readonly prisma: PrismaClient,
    private readonly sender: MessageSender,
  ) {}

  setHooks(hooks: NotificationHooks): void {
    this.hooks = hooks;
  }

  async enqueue(db: Db, input: NotificationInput | NotificationInput[]): Promise<void> {
    const list = Array.isArray(input) ? input : [input];
    if (list.length === 0) return;
    await db.notification.createMany({
      data: list.map((n) => ({
        kind: n.kind,
        chatId: n.chatId,
        text: n.text,
        replyMarkup: n.replyMarkup ? (n.replyMarkup as unknown as Prisma.InputJsonValue) : Prisma.DbNull,
        dedupKey: n.dedupKey ?? null,
        orderId: n.orderId ?? null,
      })),
      skipDuplicates: true,
    });
  }

  /** Надсилає повідомлення, час яких настав. Повертає кількість успішно надісланих. */
  async processDue(opts: { limit?: number; orderId?: number } = {}): Promise<number> {
    const limit = opts.limit ?? 25;
    const claimed = await this.prisma.$queryRaw<Array<{ id: number }>>`
      UPDATE notifications
      SET next_attempt_at = NOW() + make_interval(secs => ${LEASE_SECONDS}), attempts = attempts + 1
      WHERE id IN (
        SELECT id FROM notifications
        WHERE status = 'PENDING' AND next_attempt_at <= NOW()
          ${opts.orderId !== undefined ? Prisma.sql`AND order_id = ${opts.orderId}` : Prisma.empty}
        ORDER BY id
        LIMIT ${limit}
        FOR UPDATE SKIP LOCKED
      )
      RETURNING id`;
    if (claimed.length === 0) return 0;
    const rows = await this.prisma.notification.findMany({
      where: { id: { in: claimed.map((c) => c.id) } },
      orderBy: { id: "asc" },
    });
    let sent = 0;
    for (const n of rows) {
      if (await this.deliver(n)) sent += 1;
    }
    return sent;
  }

  private async deliver(n: Notification): Promise<boolean> {
    try {
      await this.sender.sendMessage(n.chatId.toString(), n.text, {
        parse_mode: "HTML",
        link_preview_options: { is_disabled: true },
        ...(n.replyMarkup ? { reply_markup: n.replyMarkup as unknown as InlineKeyboardMarkup } : {}),
      });
      await this.prisma.notification.update({
        where: { id: n.id },
        data: { status: "SENT", sentAt: new Date(), lastError: null },
      });
      if (this.hooks.onSent) {
        try {
          await this.hooks.onSent(n);
        } catch (err) {
          logger.error({ err, notificationId: n.id }, "Помилка обробника після надсилання сповіщення");
        }
      }
      return true;
    } catch (err) {
      const message = errorMessage(err).slice(0, 500);
      if (isUnreachableError(err)) {
        await this.prisma.notification.update({
          where: { id: n.id },
          data: { status: "FAILED", lastError: message },
        });
        logger.warn({ notificationId: n.id, kind: n.kind }, "Отримувач недоступний (заблокував бота?)");
        if (this.hooks.onUnreachable) await this.hooks.onUnreachable(n.chatId).catch(() => undefined);
        return false;
      }
      const retryAfter = retryAfterSeconds(err);
      const giveUp = retryAfter === null && n.attempts >= MAX_ATTEMPTS;
      const delaySeconds = retryAfter ?? Math.min(1800, 5 * 2 ** Math.max(0, n.attempts - 1));
      await this.prisma.notification.update({
        where: { id: n.id },
        data: giveUp
          ? { status: "FAILED", lastError: message }
          : { lastError: message, nextAttemptAt: new Date(Date.now() + delaySeconds * 1000) },
      });
      logger.warn(
        { notificationId: n.id, kind: n.kind, attempts: n.attempts, giveUp, err: message },
        "Не вдалося надіслати сповіщення",
      );
      return false;
    }
  }

  start(intervalMs = 3000): void {
    if (this.timer) return;
    const tick = () => {
      if (this.running) return;
      this.running = this.processDue()
        .then(() => undefined)
        .catch((err) => logger.error({ err }, "Помилка обробника черги сповіщень"))
        .finally(() => {
          this.running = null;
        });
    };
    this.timer = setInterval(tick, intervalMs);
    this.timer.unref();
    tick();
  }

  async stop(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    if (this.running) await this.running;
  }
}

import type { Broadcast } from "../generated/prisma/client.js";
import type { Prisma, PrismaClient } from "../database/client.js";
import { errorMessage } from "../lib/errors.js";
import { logger } from "../lib/logger.js";
import { isUnreachableError, retryAfterSeconds, type MessageSender } from "../notifications/notificationService.js";

export interface BroadcastSender extends MessageSender {
  sendPhoto(chatId: number | string, photo: string, extra?: { caption?: string; parse_mode?: "HTML" }): Promise<unknown>;
}

const RECIPIENT_FILTER: Prisma.CustomerWhereInput = {
  isBlocked: false,
  marketingOptOut: false,
  anonymizedAt: null,
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Масові розсилки покупцям. Надсилання йде у фоні з обмеженням швидкості;
 * прогрес (курсор) зберігається в БД, тож після перезапуску розсилка продовжується.
 */
export class BroadcastService {
  private loop: Promise<void> | null = null;
  private stopping = false;

  constructor(
    private readonly prisma: PrismaClient,
    private readonly sender: BroadcastSender,
    private readonly messagesPerSecond: number,
  ) {}

  recipientsCount(): Promise<number> {
    return this.prisma.customer.count({ where: RECIPIENT_FILTER });
  }

  async createDraft(adminTelegramId: bigint, text: string, photoFileId: string | null): Promise<Broadcast> {
    await this.prisma.broadcast.updateMany({
      where: { adminTelegramId, status: "DRAFT" },
      data: { status: "CANCELED" },
    });
    return this.prisma.broadcast.create({ data: { adminTelegramId, text, photoFileId } });
  }

  async latestDraft(adminTelegramId: bigint): Promise<Broadcast | null> {
    return this.prisma.broadcast.findFirst({
      where: { adminTelegramId, status: "DRAFT" },
      orderBy: { id: "desc" },
    });
  }

  /** Підтвердження адміністратора: DRAFT → SENDING. Повторне натискання нічого не змінює. */
  async confirm(broadcastId: number): Promise<Broadcast | null> {
    const total = await this.recipientsCount();
    const res = await this.prisma.broadcast.updateMany({
      where: { id: broadcastId, status: "DRAFT" },
      data: { status: "SENDING", totalRecipients: total, startedAt: new Date() },
    });
    if (res.count === 0) return null;
    this.ensureRunning();
    return this.prisma.broadcast.findUnique({ where: { id: broadcastId } });
  }

  async cancelDraft(adminTelegramId: bigint): Promise<void> {
    await this.prisma.broadcast.updateMany({
      where: { adminTelegramId, status: "DRAFT" },
      data: { status: "CANCELED" },
    });
  }

  /** Запускає фонове надсилання (також відновлює перервані розсилки після перезапуску). */
  ensureRunning(): void {
    if (this.loop || this.stopping) return;
    this.loop = this.run()
      .catch((err) => logger.error({ err }, "Помилка розсилки"))
      .finally(() => {
        this.loop = null;
      });
  }

  async stop(): Promise<void> {
    this.stopping = true;
    if (this.loop) await this.loop;
  }

  private async run(): Promise<void> {
    const delayMs = Math.ceil(1000 / this.messagesPerSecond);
    while (!this.stopping) {
      const broadcast = await this.prisma.broadcast.findFirst({ where: { status: "SENDING" }, orderBy: { id: "asc" } });
      if (!broadcast) return;
      await this.sendBatch(broadcast, delayMs);
    }
  }

  private async sendBatch(broadcast: Broadcast, delayMs: number): Promise<void> {
    const recipients = await this.prisma.customer.findMany({
      where: { ...RECIPIENT_FILTER, id: { gt: broadcast.cursorCustomerId } },
      orderBy: { id: "asc" },
      take: 25,
      select: { id: true, telegramId: true },
    });
    if (recipients.length === 0) {
      const done = await this.prisma.broadcast.update({
        where: { id: broadcast.id },
        data: { status: "DONE", finishedAt: new Date() },
      });
      await this.sender
        .sendMessage(
          done.adminTelegramId.toString(),
          `📣 Розсилку №${done.id} завершено.\nНадіслано: ${done.sentCount}\nНе доставлено: ${done.failedCount}`,
        )
        .catch((err) => logger.warn({ err: errorMessage(err) }, "Не вдалося повідомити адміністратора про розсилку"));
      return;
    }
    for (const r of recipients) {
      if (this.stopping) return;
      // Розсилку могли скасувати — перевіряємо статус перед кожним повідомленням.
      const current = await this.prisma.broadcast.findUnique({ where: { id: broadcast.id }, select: { status: true } });
      if (current?.status !== "SENDING") return;
      let delivered = false;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          if (broadcast.photoFileId) {
            await this.sender.sendPhoto(r.telegramId.toString(), broadcast.photoFileId, {
              caption: broadcast.text,
              parse_mode: "HTML",
            });
          } else {
            await this.sender.sendMessage(r.telegramId.toString(), broadcast.text, {
              parse_mode: "HTML",
              link_preview_options: { is_disabled: true },
            });
          }
          delivered = true;
          break;
        } catch (err) {
          const wait = retryAfterSeconds(err);
          if (wait !== null) {
            await sleep(wait * 1000);
            continue;
          }
          if (isUnreachableError(err)) {
            await this.prisma.customer.update({ where: { id: r.id }, data: { isBlocked: true } });
          } else {
            logger.warn({ err: errorMessage(err), customerId: r.id }, "Помилка надсилання розсилки");
          }
          break;
        }
      }
      await this.prisma.broadcast.update({
        where: { id: broadcast.id },
        data: {
          cursorCustomerId: r.id,
          ...(delivered ? { sentCount: { increment: 1 } } : { failedCount: { increment: 1 } }),
        },
      });
      await sleep(delayMs);
    }
  }
}

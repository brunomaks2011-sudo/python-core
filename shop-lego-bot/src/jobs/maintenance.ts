import { logger } from "../lib/logger.js";
import type { Services } from "../services.js";

/** Періодичне прибирання: старі update_id, історія чатів, покинуті чернетки, надіслані сповіщення. */
export class MaintenanceJob {
  private timer: NodeJS.Timeout | null = null;
  private running: Promise<void> | null = null;

  constructor(
    private readonly services: Services,
    private readonly intervalMs = 60 * 60_000,
  ) {}

  async runOnce(): Promise<void> {
    const s = this.services;
    const [updates, chats, drafts, notifications] = await Promise.all([
      s.dedup.cleanup(3),
      s.chat.cleanup(s.config.retention.chatHistoryDays),
      s.checkout.expireStale(s.config.retention.checkoutTtlHours),
      s.prisma.notification.deleteMany({
        where: { status: "SENT", sentAt: { lt: new Date(Date.now() - 30 * 86_400_000) } },
      }),
    ]);
    logger.info(
      { updates, chats, drafts, notifications: notifications.count },
      "Регламентне прибирання бази даних виконано",
    );
  }

  start(): void {
    if (this.timer) return;
    const tick = () => {
      if (this.running) return;
      this.running = this.runOnce()
        .catch((err) => logger.error({ err }, "Помилка регламентного прибирання"))
        .finally(() => {
          this.running = null;
        });
    };
    this.timer = setInterval(tick, this.intervalMs);
    this.timer.unref();
    setTimeout(tick, 30_000).unref();
  }

  async stop(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    if (this.running) await this.running;
  }
}

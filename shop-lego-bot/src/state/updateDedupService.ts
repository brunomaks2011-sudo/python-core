import type { PrismaClient } from "../database/client.js";

/**
 * Захист від повторної обробки одного оновлення Telegram (повторна доставка після
 * збою мережі, перезапуску чи повтору webhook). update_id фіксується в БД атомарно.
 */
export class UpdateDedupService {
  constructor(private readonly prisma: PrismaClient) {}

  /** true — оновлення нове й його треба обробити; false — уже оброблялося. */
  async markProcessed(botId: number, updateId: number): Promise<boolean> {
    const inserted = await this.prisma.$executeRaw`
      INSERT INTO processed_updates (bot_id, update_id)
      VALUES (${BigInt(botId)}, ${BigInt(updateId)})
      ON CONFLICT DO NOTHING`;
    return inserted === 1;
  }

  async cleanup(olderThanDays = 3): Promise<number> {
    const res = await this.prisma.processedUpdate.deleteMany({
      where: { createdAt: { lt: new Date(Date.now() - olderThanDays * 86_400_000) } },
    });
    return res.count;
  }
}

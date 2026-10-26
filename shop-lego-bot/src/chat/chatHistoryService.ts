import type { ChatMessage, ChatRole } from "../generated/prisma/client.js";
import type { PrismaClient } from "../database/client.js";

const MAX_STORED_TEXT = 1500;

/** Короткий контекст розмови для розуміння «цей набір», «а дешевше є?» тощо. */
export class ChatHistoryService {
  constructor(private readonly prisma: PrismaClient) {}

  async add(customerId: number, role: ChatRole, text: string, productIds: number[] = []): Promise<void> {
    const trimmed = text.trim().slice(0, MAX_STORED_TEXT);
    if (!trimmed && productIds.length === 0) return;
    await this.prisma.chatMessage.create({
      data: { customerId, role, text: trimmed, productIds: [...new Set(productIds)].slice(0, 20) },
    });
  }

  /** Останні повідомлення (у хронологічному порядку) за maxAgeHours годин. */
  async recent(customerId: number, limit = 8, maxAgeHours = 24): Promise<ChatMessage[]> {
    const rows = await this.prisma.chatMessage.findMany({
      where: { customerId, createdAt: { gte: new Date(Date.now() - maxAgeHours * 3600_000) } },
      orderBy: [{ createdAt: "desc" }, { id: "desc" }],
      take: limit,
    });
    return rows.reverse();
  }

  /** Товари, які бот показав покупцю останніми (для «цей набір»). */
  async lastShownProductIds(customerId: number, maxAgeHours = 24): Promise<number[]> {
    const row = await this.prisma.chatMessage.findFirst({
      where: {
        customerId,
        role: "ASSISTANT",
        productIds: { isEmpty: false },
        createdAt: { gte: new Date(Date.now() - maxAgeHours * 3600_000) },
      },
      orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    });
    return row?.productIds ?? [];
  }

  async cleanup(retentionDays: number): Promise<number> {
    const res = await this.prisma.chatMessage.deleteMany({
      where: { createdAt: { lt: new Date(Date.now() - retentionDays * 86_400_000) } },
    });
    return res.count;
  }
}

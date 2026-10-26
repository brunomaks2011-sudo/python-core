import type { Prisma, PrismaClient } from "../database/client.js";

export interface UserStateValue<T = Record<string, unknown>> {
  scene: string | null;
  data: T;
}

/** Стан покрокових сценаріїв (адмін-майстри, введення ТТН тощо) у базі даних. */
export class UserStateService {
  constructor(private readonly prisma: PrismaClient) {}

  async get<T = Record<string, unknown>>(telegramId: bigint): Promise<UserStateValue<T>> {
    const row = await this.prisma.userState.findUnique({ where: { telegramId } });
    return { scene: row?.scene ?? null, data: (row?.data ?? {}) as T };
  }

  async set(telegramId: bigint, scene: string | null, data: object = {}): Promise<void> {
    const json = data as Prisma.InputJsonValue;
    await this.prisma.userState.upsert({
      where: { telegramId },
      create: { telegramId, scene, data: json },
      update: { scene, data: json },
    });
  }

  async clear(telegramId: bigint): Promise<void> {
    await this.prisma.userState.deleteMany({ where: { telegramId } });
  }
}

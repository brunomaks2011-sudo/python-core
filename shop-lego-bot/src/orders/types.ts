import type { ActorType, Prisma } from "../generated/prisma/client.js";

export type OrderFull = Prisma.OrderGetPayload<{ include: { items: true; customer: true } }>;
export type OrderWithHistory = Prisma.OrderGetPayload<{
  include: { items: true; customer: true; history: { orderBy: { createdAt: "asc" } } };
}>;

export interface OrderActor {
  actorType: ActorType;
  actorTelegramId?: bigint | null;
}

export const ORDER_INCLUDE = { items: true, customer: true } as const;

import "server-only";
import { timingSafeEqual } from "node:crypto";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";

function safeEqual(a: string, b: string) {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

/**
 * Повертає замовлення, якщо відвідувач має до нього доступ:
 * за секретним токеном з посилання (гості) або як власник/адміністратор.
 */
export async function getAccessibleOrder(number: string, token?: string | null) {
  if (!/^[0-9]{6}-[0-9]{5}$/.test(number)) return null;
  const order = await prisma.order.findUnique({ where: { number }, include: { items: true } });
  if (!order) return null;
  if (token && safeEqual(token, order.accessToken)) return order;
  const session = await auth();
  if (session?.user && (session.user.id === order.userId || session.user.role === "ADMIN")) return order;
  return null;
}

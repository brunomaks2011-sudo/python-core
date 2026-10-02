import "server-only";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";

/** Поточний користувач або редирект на вхід. */
export async function requireUser(callbackUrl = "/account") {
  const session = await auth();
  if (!session?.user?.id) redirect(`/login?callbackUrl=${encodeURIComponent(callbackUrl)}`);
  const user = await prisma.user.findUnique({ where: { id: session.user.id } });
  if (!user) redirect("/login");
  return user;
}

export class ForbiddenError extends Error {
  constructor() {
    super("Доступ заборонено");
  }
}

/**
 * Перевірка ролі ADMIN. Роль читається з БД (а не лише з JWT),
 * тож позбавлення прав діє одразу. Викликається в КОЖНІЙ адмінській сторінці, дії та API.
 */
export async function requireAdmin() {
  const session = await auth();
  if (!session?.user?.id) redirect("/login?callbackUrl=/admin");
  const user = await prisma.user.findUnique({ where: { id: session.user.id }, select: { id: true, role: true, name: true, email: true } });
  if (!user || user.role !== "ADMIN") throw new ForbiddenError();
  return user;
}

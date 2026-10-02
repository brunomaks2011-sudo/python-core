"use server";

import { createHash, randomBytes } from "node:crypto";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { AuthError } from "next-auth";
import bcrypt from "bcryptjs";
import { z } from "zod";
import { signIn, signOut } from "@/auth";
import { prisma } from "@/lib/prisma";
import { mergeGuestCartIntoUser } from "@/lib/cart/server";
import { clientIp, rateLimit } from "@/lib/rate-limit";
import { emailSchema, fieldErrors, loginSchema, passwordSchema, registerSchema } from "@/lib/validation";
import { sendMail } from "@/lib/mail";
import { absoluteUrl, siteConfig } from "@/config/site";

export type FormState = { error?: string; fieldErrors?: Record<string, string>; success?: string } | undefined;

/** Дозволяємо лише внутрішні адреси повернення (захист від open redirect). */
function safeCallback(url: FormDataEntryValue | null): string {
  const s = typeof url === "string" ? url : "";
  return s.startsWith("/") && !s.startsWith("//") && !s.startsWith("/\\") ? s : "/account";
}

const hashToken = (t: string) => createHash("sha256").update(t).digest("hex");

export async function loginAction(_: FormState, formData: FormData): Promise<FormState> {
  const parsed = loginSchema.safeParse({ email: formData.get("email"), password: formData.get("password") });
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };

  try {
    await signIn("credentials", { ...parsed.data, redirect: false });
  } catch (e) {
    if (e instanceof AuthError) {
      const code = (e as AuthError & { code?: string }).code;
      if (code === "rate_limited") return { error: "Забагато спроб входу. Спробуйте через 15 хвилин." };
      return { error: "Невірний email або пароль" };
    }
    throw e;
  }
  const user = await prisma.user.findUnique({ where: { email: parsed.data.email }, select: { id: true, role: true } });
  if (user) await mergeGuestCartIntoUser(user.id);
  const callback = safeCallback(formData.get("callbackUrl"));
  redirect(user?.role === "ADMIN" && callback === "/account" ? "/admin" : callback);
}

export async function registerAction(_: FormState, formData: FormData): Promise<FormState> {
  const ip = clientIp(await headers());
  const limit = await rateLimit(`register:${ip}`, 5, 60 * 60 * 1000);
  if (!limit.ok) return { error: "Забагато реєстрацій з цієї адреси. Спробуйте пізніше." };

  const parsed = registerSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };
  const { name, email, phone, password } = parsed.data;

  const exists = await prisma.user.findUnique({ where: { email }, select: { id: true } });
  if (exists) return { fieldErrors: { email: "Користувач з таким email уже існує" } };

  const user = await prisma.user.create({
    data: { name, email, phone: phone || null, passwordHash: await bcrypt.hash(password, 12) },
  });
  await signIn("credentials", { email, password, redirect: false });
  await mergeGuestCartIntoUser(user.id);
  redirect(safeCallback(formData.get("callbackUrl")));
}

export async function logoutAction() {
  await signOut({ redirectTo: "/" });
}

export async function requestPasswordResetAction(_: FormState, formData: FormData): Promise<FormState> {
  const parsed = z.object({ email: emailSchema }).safeParse({ email: formData.get("email") });
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };
  const ip = clientIp(await headers());
  const [byIp, byEmail] = await Promise.all([
    rateLimit(`reset-ip:${ip}`, 10, 60 * 60 * 1000),
    rateLimit(`reset-email:${parsed.data.email}`, 3, 60 * 60 * 1000),
  ]);
  const generic = { success: "Якщо акаунт з таким email існує, ми надіслали лист з посиланням для зміни пароля." };
  if (!byIp.ok) return { error: "Забагато запитів. Спробуйте пізніше." };
  if (!byEmail.ok) return generic;

  const user = await prisma.user.findUnique({ where: { email: parsed.data.email } });
  if (user) {
    const token = randomBytes(32).toString("base64url");
    await prisma.passwordResetToken.deleteMany({ where: { userId: user.id } });
    await prisma.passwordResetToken.create({
      data: { userId: user.id, tokenHash: hashToken(token), expiresAt: new Date(Date.now() + 60 * 60 * 1000) },
    });
    const link = absoluteUrl(`/reset-password?token=${token}`);
    await sendMail({
      to: user.email,
      subject: `Відновлення пароля — ${siteConfig.name}`,
      text: `Вітаємо, ${user.name}!\n\nЩоб встановити новий пароль, перейдіть за посиланням (діє 1 годину):\n${link}\n\nЯкщо ви не робили запит — просто проігноруйте цей лист.`,
    });
  }
  // Однакова відповідь незалежно від існування акаунта (без перебору email)
  return generic;
}

export async function resetPasswordAction(_: FormState, formData: FormData): Promise<FormState> {
  const parsed = z
    .object({ token: z.string().min(20).max(100), password: passwordSchema, confirm: z.string() })
    .refine((d) => d.password === d.confirm, { path: ["confirm"], message: "Паролі не збігаються" })
    .safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };

  const record = await prisma.passwordResetToken.findUnique({ where: { tokenHash: hashToken(parsed.data.token) } });
  if (!record || record.usedAt || record.expiresAt < new Date()) {
    return { error: "Посилання недійсне або застаріле. Запросіть нове." };
  }
  await prisma.$transaction([
    prisma.user.update({ where: { id: record.userId }, data: { passwordHash: await bcrypt.hash(parsed.data.password, 12) } }),
    prisma.passwordResetToken.update({ where: { id: record.id }, data: { usedAt: new Date() } }),
  ]);
  return { success: "Пароль змінено. Тепер ви можете увійти з новим паролем." };
}

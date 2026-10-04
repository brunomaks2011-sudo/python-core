"use server";

import bcrypt from "bcryptjs";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { prisma } from "@/lib/prisma";
import { requireUser } from "@/lib/auth-guards";
import { cuidSchema, fieldErrors, nameSchema, passwordSchema, phoneSchema } from "@/lib/validation";
import { deliverySchema } from "@/lib/orders/schema";
import type { FormState } from "./auth";

export async function updateProfileAction(_: FormState, formData: FormData): Promise<FormState> {
  const user = await requireUser();
  const parsed = z
    .object({ name: nameSchema, phone: z.union([z.literal(""), phoneSchema]) })
    .safeParse({ name: formData.get("name"), phone: formData.get("phone") ?? "" });
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };
  await prisma.user.update({ where: { id: user.id }, data: { name: parsed.data.name, phone: parsed.data.phone || null } });
  revalidatePath("/account");
  return { success: "Профіль збережено" };
}

export async function changePasswordAction(_: FormState, formData: FormData): Promise<FormState> {
  const user = await requireUser();
  const parsed = z
    .object({ current: z.string().min(1, "Вкажіть поточний пароль"), password: passwordSchema, confirm: z.string() })
    .refine((d) => d.password === d.confirm, { path: ["confirm"], message: "Паролі не збігаються" })
    .safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };
  if (!(await bcrypt.compare(parsed.data.current, user.passwordHash))) {
    return { fieldErrors: { current: "Невірний поточний пароль" } };
  }
  await prisma.user.update({ where: { id: user.id }, data: { passwordHash: await bcrypt.hash(parsed.data.password, 12) } });
  return { success: "Пароль змінено" };
}

export async function addAddressAction(_: FormState, formData: FormData): Promise<FormState> {
  const user = await requireUser();
  const raw = Object.fromEntries([...formData.entries()].filter(([, v]) => v !== "").map(([k, v]) => [k, String(v)]));
  const parsed = z
    .object({ label: z.string().trim().max(60).optional(), recipientName: nameSchema, recipientPhone: phoneSchema })
    .and(deliverySchema)
    .safeParse({ ...raw, method: raw.deliveryMethod });
  if (!parsed.success) return { fieldErrors: fieldErrors(parsed.error) };
  const d = parsed.data;
  if (d.method === "PICKUP") return { error: "Для самовивозу адреса не потрібна" };
  if ((await prisma.address.count({ where: { userId: user.id } })) >= 20) return { error: "Можна зберегти до 20 адрес" };
  const isFirst = (await prisma.address.count({ where: { userId: user.id } })) === 0;
  await prisma.address.create({
    data: {
      userId: user.id,
      label: d.label,
      recipientName: d.recipientName,
      recipientPhone: d.recipientPhone,
      deliveryMethod: d.method,
      city: d.city,
      warehouse: "warehouse" in d ? d.warehouse : null,
      street: "street" in d ? d.street : null,
      building: "building" in d ? d.building : null,
      apartment: "apartment" in d ? d.apartment : null,
      postalCode: "postalCode" in d ? d.postalCode : null,
      isDefault: isFirst,
    },
  });
  revalidatePath("/account/addresses");
  return { success: "Адресу збережено" };
}

export async function deleteAddressAction(formData: FormData) {
  const user = await requireUser();
  const id = cuidSchema.parse(formData.get("id"));
  await prisma.address.deleteMany({ where: { id, userId: user.id } });
  revalidatePath("/account/addresses");
}

export async function setDefaultAddressAction(formData: FormData) {
  const user = await requireUser();
  const id = cuidSchema.parse(formData.get("id"));
  const addr = await prisma.address.findFirst({ where: { id, userId: user.id } });
  if (!addr) return;
  await prisma.$transaction([
    prisma.address.updateMany({ where: { userId: user.id }, data: { isDefault: false } }),
    prisma.address.update({ where: { id }, data: { isDefault: true } }),
  ]);
  revalidatePath("/account/addresses");
}

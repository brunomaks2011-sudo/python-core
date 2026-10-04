import { z } from "zod";

// Спільні схеми валідації (використовуються на сервері).

export const emailSchema = z
  .string({ error: "Вкажіть email" })
  .trim()
  .toLowerCase()
  .max(254)
  .pipe(z.email({ error: "Некоректний email" }));

export const passwordSchema = z
  .string({ error: "Вкажіть пароль" })
  .min(8, "Пароль має містити щонайменше 8 символів")
  .max(128, "Пароль задовгий");

/** Український номер: +380XXXXXXXXX. Приймає 0XXXXXXXXX, 380..., з пробілами/дужками. */
export const phoneSchema = z
  .string({ error: "Вкажіть телефон" })
  .trim()
  .transform((v) => v.replace(/[\s()-]/g, ""))
  .transform((v) => (v.startsWith("0") && v.length === 10 ? `+38${v}` : v.startsWith("380") ? `+${v}` : v))
  .pipe(z.string().regex(/^\+380\d{9}$/, "Телефон у форматі +380XXXXXXXXX"));

export const nameSchema = z.string({ error: "Вкажіть ім'я" }).trim().min(2, "Вкажіть ім'я").max(100);

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Вкажіть пароль").max(128),
});

export const registerSchema = z
  .object({
    name: nameSchema,
    email: emailSchema,
    phone: z.union([z.literal(""), phoneSchema]).optional(),
    password: passwordSchema,
    confirm: z.string(),
  })
  .refine((d) => d.password === d.confirm, { path: ["confirm"], message: "Паролі не збігаються" });

export const cuidSchema = z.string().min(1).max(64).regex(/^[a-z0-9]+$/i);

export const quantitySchema = z.coerce.number().int().min(0).max(99);

/** Перетворює помилки Zod на { поле: повідомлення } для форм. */
export function fieldErrors(error: z.ZodError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const issue of error.issues) {
    const key = issue.path.join(".") || "_form";
    if (!out[key]) out[key] = issue.message;
  }
  return out;
}

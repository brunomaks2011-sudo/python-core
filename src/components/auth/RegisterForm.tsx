"use client";

import Link from "next/link";
import { useActionState } from "react";
import { registerAction } from "@/app/actions/auth";
import { Field, FormMessage } from "@/components/ui/Field";

export function RegisterForm({ callbackUrl }: { callbackUrl?: string }) {
  const [state, action, pending] = useActionState(registerAction, undefined);
  const fe = state?.fieldErrors ?? {};
  return (
    <form action={action} className="space-y-4" noValidate>
      <input type="hidden" name="callbackUrl" value={callbackUrl ?? ""} />
      <FormMessage error={state?.error} />
      <Field label="Ім'я" name="name" autoComplete="name" required error={fe.name} />
      <Field label="Email" name="email" type="email" autoComplete="email" required error={fe.email} />
      <Field label="Телефон (необов'язково)" name="phone" type="tel" autoComplete="tel" placeholder="+380" error={fe.phone} />
      <Field label="Пароль" name="password" type="password" autoComplete="new-password" minLength={8} required error={fe.password} />
      <Field label="Повторіть пароль" name="confirm" type="password" autoComplete="new-password" required error={fe.confirm} />
      <button className="btn-primary w-full py-3" disabled={pending}>{pending ? "Створюємо…" : "Зареєструватися"}</button>
      <p className="text-center text-sm text-ink/60">
        Вже маєте акаунт? <Link href="/login" className="font-bold text-sky-brand hover:underline">Увійти</Link>
      </p>
    </form>
  );
}

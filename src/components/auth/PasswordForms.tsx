"use client";

import Link from "next/link";
import { useActionState } from "react";
import { requestPasswordResetAction, resetPasswordAction } from "@/app/actions/auth";
import { Field, FormMessage } from "@/components/ui/Field";

export function ForgotPasswordForm() {
  const [state, action, pending] = useActionState(requestPasswordResetAction, undefined);
  return (
    <form action={action} className="space-y-4" noValidate>
      <FormMessage error={state?.error} success={state?.success} />
      <Field label="Email" name="email" type="email" autoComplete="email" required error={state?.fieldErrors?.email} />
      <button className="btn-primary w-full py-3" disabled={pending}>{pending ? "Надсилаємо…" : "Надіслати посилання"}</button>
      <p className="text-center text-sm"><Link href="/login" className="font-bold text-sky-brand hover:underline">← Повернутися до входу</Link></p>
    </form>
  );
}

export function ResetPasswordForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(resetPasswordAction, undefined);
  if (state?.success) {
    return (
      <div className="space-y-4">
        <FormMessage success={state.success} />
        <Link href="/login" className="btn-primary w-full">Увійти</Link>
      </div>
    );
  }
  return (
    <form action={action} className="space-y-4" noValidate>
      <input type="hidden" name="token" value={token} />
      <FormMessage error={state?.error ?? state?.fieldErrors?.token} />
      <Field label="Новий пароль" name="password" type="password" autoComplete="new-password" minLength={8} required error={state?.fieldErrors?.password} />
      <Field label="Повторіть пароль" name="confirm" type="password" autoComplete="new-password" required error={state?.fieldErrors?.confirm} />
      <button className="btn-primary w-full py-3" disabled={pending}>{pending ? "Зберігаємо…" : "Змінити пароль"}</button>
    </form>
  );
}

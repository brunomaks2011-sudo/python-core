"use client";

import { ActionForm } from "@/components/ui/ActionForm";
import Link from "next/link";
import { useActionState } from "react";
import { loginAction } from "@/app/actions/auth";
import { Field, FormMessage } from "@/components/ui/Field";

export function LoginForm({ callbackUrl }: { callbackUrl?: string }) {
  const [state, action, pending] = useActionState(loginAction, undefined);
  return (
    <ActionForm action={action} className="space-y-4" noValidate>
      <input type="hidden" name="callbackUrl" value={callbackUrl ?? ""} />
      <FormMessage error={state?.error} />
      <Field label="Email" name="email" type="email" autoComplete="email" required error={state?.fieldErrors?.email} />
      <Field label="Пароль" name="password" type="password" autoComplete="current-password" required error={state?.fieldErrors?.password} />
      <div className="text-right text-sm">
        <Link href="/forgot-password" className="font-bold text-sky-brand hover:underline">Забули пароль?</Link>
      </div>
      <button className="btn-primary w-full py-3" disabled={pending}>{pending ? "Входимо…" : "Увійти"}</button>
      <p className="text-center text-sm text-ink/60">
        Немає акаунта?{" "}
        <Link href={`/register${callbackUrl ? `?callbackUrl=${encodeURIComponent(callbackUrl)}` : ""}`} className="font-bold text-sky-brand hover:underline">Зареєструватися</Link>
      </p>
    </ActionForm>
  );
}

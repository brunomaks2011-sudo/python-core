"use client";

import { useActionState } from "react";
import { changePasswordAction, updateProfileAction } from "@/app/actions/account";
import { Field, FormMessage } from "@/components/ui/Field";

export function ProfileForm({ name, phone, email }: { name: string; phone: string; email: string }) {
  const [state, action, pending] = useActionState(updateProfileAction, undefined);
  return (
    <form action={action} className="card space-y-4 p-6">
      <h2 className="text-xl font-black">Профіль</h2>
      <FormMessage error={state?.error} success={state?.success} />
      <Field label="Ім'я" name="name" defaultValue={name} autoComplete="name" error={state?.fieldErrors?.name} />
      <Field label="Телефон" name="phone" type="tel" defaultValue={phone} placeholder="+380" autoComplete="tel" error={state?.fieldErrors?.phone} />
      <Field label="Email" name="email_ro" defaultValue={email} disabled />
      <button className="btn-primary" disabled={pending}>{pending ? "Зберігаємо…" : "Зберегти"}</button>
    </form>
  );
}

export function ChangePasswordForm() {
  const [state, action, pending] = useActionState(changePasswordAction, undefined);
  return (
    <form action={action} className="card space-y-4 p-6">
      <h2 className="text-xl font-black">Зміна пароля</h2>
      <FormMessage error={state?.error} success={state?.success} />
      <Field label="Поточний пароль" name="current" type="password" autoComplete="current-password" error={state?.fieldErrors?.current} />
      <Field label="Новий пароль" name="password" type="password" autoComplete="new-password" error={state?.fieldErrors?.password} />
      <Field label="Повторіть новий пароль" name="confirm" type="password" autoComplete="new-password" error={state?.fieldErrors?.confirm} />
      <button className="btn-secondary" disabled={pending}>{pending ? "Зберігаємо…" : "Змінити пароль"}</button>
    </form>
  );
}

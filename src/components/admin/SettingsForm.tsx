"use client";

import { ActionForm } from "@/components/ui/ActionForm";
import { useActionState } from "react";
import { saveSettingsAction } from "@/app/admin/actions";
import { FormMessage } from "@/components/ui/Field";
import type { ShopSettings } from "@/lib/settings";

const FIELDS: { key: keyof ShopSettings; label: string; hint: string }[] = [
  { key: "freeShippingThreshold", label: "Безкоштовна доставка від, ₴", hint: "0 — вимкнути безкоштовну доставку" },
  { key: "ukrposhtaRate", label: "Тариф Укрпошти, ₴", hint: "Фіксована вартість доставки Укрпоштою" },
  { key: "npWarehouseFallbackRate", label: "Нова Пошта: резервний тариф (відділення/поштомат), ₴", hint: "Якщо API Нової Пошти недоступне або ключ не задано" },
  { key: "npCourierFallbackRate", label: "Нова Пошта: резервний тариф (кур'єр), ₴", hint: "Якщо API Нової Пошти недоступне або ключ не задано" },
];

export function SettingsForm({ settings }: { settings: ShopSettings }) {
  const [state, action, pending] = useActionState(saveSettingsAction, undefined);
  return (
    <ActionForm action={action} className="max-w-xl space-y-4 rounded-2xl bg-white p-5 shadow-sm">
      <FormMessage error={state?.error} success={state?.success} />
      {FIELDS.map((f) => (
        <div key={f.key}>
          <label className="label" htmlFor={`s-${f.key}`}>{f.label}</label>
          <input id={`s-${f.key}`} name={f.key} type="number" min="0" step="0.01" defaultValue={settings[f.key] / 100} className="input" required />
          <p className="mt-1 text-xs text-ink/50">{state?.fieldErrors?.[f.key] ?? f.hint}</p>
        </div>
      ))}
      <button className="btn-primary" disabled={pending}>{pending ? "Зберігаємо…" : "Зберегти"}</button>
    </ActionForm>
  );
}

"use client";

import { ActionForm } from "@/components/ui/ActionForm";
import { useActionState, useState } from "react";
import { addAddressAction } from "@/app/actions/account";
import { Field, FormMessage } from "@/components/ui/Field";

export function AddressForm({ defaultName, defaultPhone }: { defaultName: string; defaultPhone: string }) {
  const [state, action, pending] = useActionState(addAddressAction, undefined);
  const [method, setMethod] = useState("NP_WAREHOUSE");
  const fe = state?.fieldErrors ?? {};
  return (
    <ActionForm action={action} className="card space-y-4 p-6">
      <h2 className="text-xl font-black">Нова адреса</h2>
      <FormMessage error={state?.error} success={state?.success} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Назва (напр. «Дім»)" name="label" maxLength={60} />
        <div>
          <label className="label" htmlFor="f-deliveryMethod">Спосіб доставки</label>
          <select id="f-deliveryMethod" name="deliveryMethod" className="input" value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="NP_WAREHOUSE">Нова Пошта — відділення</option>
            <option value="NP_POSTOMAT">Нова Пошта — поштомат</option>
            <option value="NP_COURIER">Нова Пошта — кур&apos;єр</option>
            <option value="UKRPOSHTA">Укрпошта</option>
          </select>
        </div>
        <Field label="Отримувач" name="recipientName" defaultValue={defaultName} error={fe.recipientName} />
        <Field label="Телефон отримувача" name="recipientPhone" type="tel" defaultValue={defaultPhone} error={fe.recipientPhone} />
        <Field label="Місто" name="city" error={fe.city} />
        {(method === "NP_WAREHOUSE" || method === "NP_POSTOMAT") && (
          <Field label={method === "NP_POSTOMAT" ? "Поштомат" : "Відділення"} name="warehouse" error={fe.warehouse} />
        )}
        {method === "UKRPOSHTA" && <Field label="Індекс" name="postalCode" inputMode="numeric" maxLength={5} error={fe.postalCode} />}
        {(method === "NP_COURIER" || method === "UKRPOSHTA") && (
          <>
            <Field label="Вулиця" name="street" error={fe.street} />
            <Field label="Будинок" name="building" error={fe.building} />
          </>
        )}
        {method === "NP_COURIER" && <Field label="Квартира" name="apartment" error={fe.apartment} />}
      </div>
      <button className="btn-primary" disabled={pending}>{pending ? "Зберігаємо…" : "Зберегти адресу"}</button>
    </ActionForm>
  );
}

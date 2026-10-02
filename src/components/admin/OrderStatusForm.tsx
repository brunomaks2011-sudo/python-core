"use client";

import { ActionForm } from "@/components/ui/ActionForm";
import { useActionState } from "react";
import type { OrderStatus } from "@prisma/client";
import { updateOrderAction } from "@/app/admin/actions";
import { ORDER_STATUS } from "@/lib/orders/labels";
import { FormMessage } from "@/components/ui/Field";

export function OrderStatusForm({ id, status, trackingNumber }: { id: string; status: OrderStatus; trackingNumber: string | null }) {
  const [state, action, pending] = useActionState(updateOrderAction, undefined);
  return (
    <ActionForm action={action} className="space-y-3">
      <input type="hidden" name="id" value={id} />
      <FormMessage error={state?.error} success={state?.success} />
      <div>
        <label className="label" htmlFor="o-status">Статус замовлення</label>
        <select id="o-status" name="status" defaultValue={status} className="input">
          {(Object.keys(ORDER_STATUS) as OrderStatus[]).map((s) => (
            <option key={s} value={s}>{ORDER_STATUS[s].label}</option>
          ))}
        </select>
        <p className="mt-1 text-xs text-ink/50">Скасування повертає товари на склад.</p>
      </div>
      <div>
        <label className="label" htmlFor="o-ttn">Номер ТТН</label>
        <input id="o-ttn" name="trackingNumber" defaultValue={trackingNumber ?? ""} placeholder="20450000000000" className="input font-mono" />
        {state?.fieldErrors?.trackingNumber && <p className="field-error">{state.fieldErrors.trackingNumber}</p>}
      </div>
      <button className="btn-primary w-full" disabled={pending}>{pending ? "Зберігаємо…" : "Зберегти"}</button>
    </ActionForm>
  );
}

"use client";

import { ActionForm } from "@/components/ui/ActionForm";
import { useActionState } from "react";
import { deleteCategoryAction, saveCategoryAction } from "@/app/admin/actions";
import { FormMessage } from "@/components/ui/Field";

type Category = { id: string; name: string; slug: string; description: string | null; sortOrder: number };

export function CategoryForm({ category }: { category?: Category }) {
  const [state, action, pending] = useActionState(saveCategoryAction, undefined);
  const fe = state?.fieldErrors ?? {};
  return (
    <ActionForm action={action} className="space-y-3">
      {category && <input type="hidden" name="id" value={category.id} />}
      <FormMessage error={state?.error} success={state?.success} />
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_90px]">
        <div>
          <input name="name" className="input" placeholder="Назва" defaultValue={category?.name} required aria-label="Назва" />
          {fe.name && <p className="field-error">{fe.name}</p>}
        </div>
        <div>
          <input name="slug" className="input" placeholder="slug (необов'язково)" defaultValue={category?.slug} aria-label="Slug" />
          {fe.slug && <p className="field-error">{fe.slug}</p>}
        </div>
        <input name="sortOrder" type="number" min="0" className="input" defaultValue={category?.sortOrder ?? 0} aria-label="Порядок" title="Порядок сортування" />
      </div>
      <textarea name="description" className="input" placeholder="Опис" defaultValue={category?.description ?? ""} aria-label="Опис" />
      <div className="flex flex-wrap items-center gap-3">
        <input name="image" type="file" accept="image/jpeg,image/png,image/webp,image/avif" className="text-xs" aria-label="Зображення" />
        <button className="btn-primary py-2" disabled={pending}>{category ? "Зберегти" : "Додати категорію"}</button>
      </div>
    </ActionForm>
  );
}

export function DeleteCategoryForm({ id, name }: { id: string; name: string }) {
  const [state, action, pending] = useActionState(deleteCategoryAction, undefined);
  return (
    <ActionForm
      action={action}
      onSubmit={(e) => {
        if (!confirm(`Видалити категорію «${name}»?`)) e.preventDefault();
      }}
    >
      <input type="hidden" name="id" value={id} />
      <button className="text-sm font-bold text-tomato-600" disabled={pending}>Видалити категорію</button>
      {state?.error && <p className="field-error">{state.error}</p>}
    </ActionForm>
  );
}

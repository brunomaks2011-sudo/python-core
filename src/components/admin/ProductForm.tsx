"use client";

/* eslint-disable @next/next/no-img-element */
import { ActionForm } from "@/components/ui/ActionForm";
import Link from "next/link";
import { useActionState, useState } from "react";
import { saveProductAction } from "@/app/admin/actions";
import { FormMessage } from "@/components/ui/Field";

type Product = {
  id: string;
  name: string;
  slug: string;
  sku: string;
  description: string;
  categoryId: string;
  price: number;
  oldPrice: number | null;
  stock: number;
  pieces: number;
  ageMin: number;
  weightGrams: number;
  isActive: boolean;
  isFeatured: boolean;
  images: string[];
};

const MAX_TOTAL = 10 * 1024 * 1024;

export function ProductForm({ product, categories }: { product?: Product; categories: { id: string; name: string }[] }) {
  const [state, action, pending] = useActionState(saveProductAction, undefined);
  const [images, setImages] = useState<string[]>(product?.images ?? []);
  const [fileError, setFileError] = useState<string | null>(null);
  const fe = state?.fieldErrors ?? {};

  const field = (name: keyof Product | string, label: string, input: React.ReactNode) => (
    <div>
      <label className="label" htmlFor={`p-${name}`}>{label}</label>
      {input}
      {fe[name] && <p className="field-error">{fe[name]}</p>}
    </div>
  );
  const move = (i: number, d: -1 | 1) =>
    setImages((list) => {
      const next = [...list];
      const j = i + d;
      if (j < 0 || j >= next.length) return list;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  return (
    <ActionForm action={action} className="space-y-6">
      {product && <input type="hidden" name="id" value={product.id} />}
      {images.map((src) => <input key={src} type="hidden" name="images" value={src} />)}
      <FormMessage error={state?.error} />

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div className="space-y-4 rounded-2xl bg-white p-5 shadow-sm">
          {field("name", "Назва", <input id="p-name" name="name" className="input" required defaultValue={product?.name} />)}
          <div className="grid gap-4 sm:grid-cols-2">
            {field("sku", "Артикул", <input id="p-sku" name="sku" className="input" required defaultValue={product?.sku} />)}
            {field("slug", "URL (slug) — порожньо = автоматично", <input id="p-slug" name="slug" className="input" defaultValue={product?.slug} placeholder="pozhezhna-stantsiia-60401" />)}
          </div>
          {field("categoryId", "Категорія (серія)", (
            <select id="p-categoryId" name="categoryId" className="input" defaultValue={product?.categoryId} required>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          ))}
          {field("description", "Опис", <textarea id="p-description" name="description" className="input min-h-40" required defaultValue={product?.description} />)}
        </div>

        <div className="space-y-4 rounded-2xl bg-white p-5 shadow-sm">
          <div className="grid grid-cols-2 gap-4">
            {field("price", "Ціна, ₴", <input id="p-price" name="price" type="number" step="0.01" min="0" className="input" required defaultValue={product ? product.price / 100 : ""} />)}
            {field("oldPrice", "Стара ціна, ₴", <input id="p-oldPrice" name="oldPrice" type="number" step="0.01" min="0" className="input" defaultValue={product?.oldPrice ? product.oldPrice / 100 : ""} />)}
            {field("stock", "Залишок, шт.", <input id="p-stock" name="stock" type="number" min="0" className="input" required defaultValue={product?.stock ?? 0} />)}
            {field("pieces", "Деталей", <input id="p-pieces" name="pieces" type="number" min="1" className="input" required defaultValue={product?.pieces} />)}
            {field("ageMin", "Вік від, років", <input id="p-ageMin" name="ageMin" type="number" min="0" className="input" required defaultValue={product?.ageMin ?? 6} />)}
            {field("weightGrams", "Вага, г", <input id="p-weightGrams" name="weightGrams" type="number" min="1" className="input" required defaultValue={product?.weightGrams ?? 500} />)}
          </div>
          <label className="flex items-center gap-2 text-sm font-bold">
            <input type="checkbox" name="isActive" defaultChecked={product?.isActive ?? true} className="h-4 w-4 accent-tomato-500" /> Активний (показувати на сайті)
          </label>
          <label className="flex items-center gap-2 text-sm font-bold">
            <input type="checkbox" name="isFeatured" defaultChecked={product?.isFeatured ?? false} className="h-4 w-4 accent-tomato-500" /> Популярний (на головній)
          </label>
        </div>
      </div>

      <div className="rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="mb-3 font-black">Зображення</h2>
        {fe.images && <p className="field-error mb-2">Некоректний список зображень</p>}
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {images.map((src, i) => (
            <li key={src} className="overflow-hidden rounded-xl border-2 border-ink/5">
              <img src={src} alt="" className="aspect-square w-full object-cover" />
              <div className="flex justify-between bg-ink/5 p-1 text-xs">
                <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="px-2 disabled:opacity-30" aria-label="Вліво">←</button>
                <button type="button" onClick={() => setImages((l) => l.filter((x) => x !== src))} className="px-2 font-bold text-tomato-600">Видалити</button>
                <button type="button" onClick={() => move(i, 1)} disabled={i === images.length - 1} className="px-2 disabled:opacity-30" aria-label="Вправо">→</button>
              </div>
              {i === 0 && <p className="bg-brand-100 text-center text-[10px] font-bold">Головне</p>}
            </li>
          ))}
        </ul>
        <div className="mt-4">
          <label className="label" htmlFor="p-newImages">Додати зображення (JPG, PNG, WEBP, AVIF; до 5 МБ кожне, до 10 МБ разом)</label>
          <input
            id="p-newImages"
            name="newImages"
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp,image/avif"
            className="block text-sm file:mr-3 file:rounded-full file:border-0 file:bg-brand-400 file:px-4 file:py-2 file:font-bold"
            onChange={(e) => {
              const files = [...(e.target.files ?? [])];
              const total = files.reduce((s, f) => s + f.size, 0);
              const tooBig = files.find((f) => f.size > 5 * 1024 * 1024);
              const msg = tooBig ? `«${tooBig.name}» більший за 5 МБ` : total > MAX_TOTAL ? "Разом більше 10 МБ — завантажте частинами" : null;
              setFileError(msg);
              if (msg) e.target.value = "";
            }}
          />
          {fileError && <p className="field-error">{fileError}</p>}
        </div>
      </div>

      <div className="flex gap-3">
        <button className="btn-primary px-8" disabled={pending}>{pending ? "Зберігаємо…" : "Зберегти"}</button>
        <Link href="/admin/products" className="btn-ghost">Скасувати</Link>
      </div>
    </ActionForm>
  );
}

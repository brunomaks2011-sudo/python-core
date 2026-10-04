"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { setCartItemQuantity } from "@/app/actions/cart";
import { ProductImage } from "@/components/ui/ProductImage";
import { formatUAH } from "@/lib/money";
import { cn } from "@/lib/utils";

type Props = {
  productId: string;
  name: string;
  slug: string;
  sku: string;
  image?: string;
  price: number;
  quantity: number;
  stock: number;
  isActive: boolean;
};

export function CartItemRow(p: Props) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const unavailable = !p.isActive || p.stock <= 0;
  const max = Math.min(p.stock, 99);

  const update = (qty: number) =>
    start(async () => {
      const res = await setCartItemQuantity(p.productId, qty);
      setError(res.ok ? (res.message ?? null) : res.error);
    });

  return (
    <li className={cn("flex gap-4 py-4", pending && "opacity-60")}>
      <Link href={`/product/${p.slug}`} className="w-20 shrink-0 overflow-hidden rounded-xl bg-brand-50 sm:w-28">
        <ProductImage src={p.image} alt={p.name} />
      </Link>
      <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center">
        <div className="flex-1">
          <Link href={`/product/${p.slug}`} className="font-bold hover:text-sky-brand">{p.name}</Link>
          <p className="text-xs text-ink/50">Арт. {p.sku} · {formatUAH(p.price)} / шт.</p>
          {unavailable && <p className="mt-1 text-xs font-bold text-tomato-600">Немає в наявності — видаліть товар з кошика</p>}
          {!unavailable && p.quantity > p.stock && (
            <p className="mt-1 text-xs font-bold text-tomato-600">Доступно лише {p.stock} шт.</p>
          )}
          {error && <p className="mt-1 text-xs font-bold text-tomato-600">{error}</p>}
        </div>
        <div className="flex items-center justify-between gap-4 sm:justify-end">
          <div className="flex items-center rounded-full border-2 border-ink/10 bg-white">
            <button type="button" disabled={pending || p.quantity <= 1} onClick={() => update(p.quantity - 1)} className="px-3 py-1.5 text-lg font-bold disabled:opacity-30" aria-label="Зменшити">−</button>
            <span className="w-8 text-center font-bold" aria-label="Кількість">{p.quantity}</span>
            <button type="button" disabled={pending || unavailable || p.quantity >= max} onClick={() => update(p.quantity + 1)} className="px-3 py-1.5 text-lg font-bold disabled:opacity-30" aria-label="Збільшити">+</button>
          </div>
          <p className="w-24 text-right font-black">{formatUAH(p.price * p.quantity)}</p>
          <button type="button" disabled={pending} onClick={() => update(0)} className="rounded-full p-2 text-ink/40 hover:bg-tomato-500/10 hover:text-tomato-600" aria-label={`Видалити ${p.name}`}>
            ✕
          </button>
        </div>
      </div>
    </li>
  );
}

"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { addToCart } from "@/app/actions/cart";
import { cn } from "@/lib/utils";

export function AddToCartButton({
  productId,
  disabled,
  compact,
  maxQuantity = 99,
}: {
  productId: string;
  disabled?: boolean;
  compact?: boolean;
  maxQuantity?: number;
}) {
  const [pending, startTransition] = useTransition();
  const [qty, setQty] = useState(1);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  const add = () =>
    startTransition(async () => {
      const res = await addToCart(productId, qty);
      setMessage(res.ok ? { text: res.message ?? "Додано в кошик", ok: true } : { text: res.error, ok: false });
    });

  if (disabled) {
    return (
      <button type="button" disabled className={cn("btn-ghost w-full", compact && "py-2")}>
        Немає в наявності
      </button>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        {!compact && (
          <div className="flex items-center rounded-full border-2 border-ink/10 bg-white">
            <button type="button" className="px-3 py-2 text-lg font-bold" onClick={() => setQty((q) => Math.max(1, q - 1))} aria-label="Зменшити кількість">−</button>
            <input
              type="number"
              min={1}
              max={maxQuantity}
              value={qty}
              onChange={(e) => setQty(Math.max(1, Math.min(maxQuantity, Number(e.target.value) || 1)))}
              className="w-12 bg-transparent text-center font-bold outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
              aria-label="Кількість"
            />
            <button type="button" className="px-3 py-2 text-lg font-bold" onClick={() => setQty((q) => Math.min(maxQuantity, q + 1))} aria-label="Збільшити кількість">+</button>
          </div>
        )}
        <button type="button" onClick={add} disabled={pending} className={cn("btn-primary flex-1", compact && "py-2")}>
          {pending ? "Додаємо…" : "Додати в кошик"}
        </button>
      </div>
      <p aria-live="polite" className={cn("min-h-4 text-xs font-semibold", message?.ok ? "text-emerald-700" : "text-tomato-600")}>
        {message && (
          <>
            {message.text}
            {message.ok && (
              <>
                {" · "}
                <Link href="/cart" className="underline">Перейти в кошик</Link>
              </>
            )}
          </>
        )}
      </p>
    </div>
  );
}

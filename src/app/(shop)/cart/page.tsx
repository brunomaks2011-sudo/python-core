import Link from "next/link";
import type { Metadata } from "next";
import { getCart } from "@/lib/cart/server";
import { getShopSettings } from "@/lib/settings";
import { formatUAH } from "@/lib/money";
import { pluralUk } from "@/lib/utils";
import { CartItemRow } from "@/components/cart/CartItemRow";
import { FreeShippingBar } from "@/components/cart/FreeShippingBar";

export const metadata: Metadata = { title: "Кошик", robots: { index: false } };

export default async function CartPage() {
  const [cart, settings] = await Promise.all([getCart(), getShopSettings()]);

  if (cart.items.length === 0) {
    return (
      <div className="container-page py-16 text-center">
        <p className="text-6xl" aria-hidden>🛒</p>
        <h1 className="mt-4 text-3xl font-black">Кошик порожній</h1>
        <p className="mt-2 text-ink/60">Додайте набори з каталогу — і повертайтеся сюди.</p>
        <Link href="/catalog" className="btn-primary mt-6">До каталогу</Link>
      </div>
    );
  }

  return (
    <div className="container-page py-8">
      <h1 className="text-3xl font-black">Кошик</h1>
      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_360px]">
        <section className="card px-4 sm:px-6">
          <ul className="divide-y divide-ink/5">
            {cart.items.map((i) => (
              <CartItemRow
                key={i.id}
                productId={i.productId}
                name={i.product.name}
                slug={i.product.slug}
                sku={i.product.sku}
                image={i.product.images[0]}
                price={i.product.price}
                quantity={i.quantity}
                stock={i.product.stock}
                isActive={i.product.isActive}
              />
            ))}
          </ul>
        </section>
        <aside className="card h-fit space-y-4 p-6 lg:sticky lg:top-24">
          <h2 className="text-xl font-black">Разом</h2>
          <div className="flex justify-between text-sm">
            <span>{cart.itemsCount} {pluralUk(cart.itemsCount, ["товар", "товари", "товарів"])}</span>
            <span className="font-bold">{formatUAH(cart.itemsTotal)}</span>
          </div>
          <div className="flex justify-between text-sm text-ink/60">
            <span>Доставка</span>
            <span>розраховується при оформленні</span>
          </div>
          <div className="flex items-baseline justify-between border-t-2 border-dashed border-ink/10 pt-4">
            <span className="font-bold">До сплати</span>
            <span className="text-2xl font-black">{formatUAH(cart.itemsTotal)}</span>
          </div>
          <FreeShippingBar itemsTotal={cart.itemsTotal} threshold={settings.freeShippingThreshold} />
          {cart.hasUnavailable ? (
            <p className="rounded-xl bg-tomato-500/10 p-3 text-sm font-bold text-tomato-600">
              Деяких товарів немає в потрібній кількості. Змініть кількість або видаліть їх.
            </p>
          ) : (
            <Link href="/checkout" className="btn-primary w-full py-3 text-base">Оформити замовлення</Link>
          )}
          <Link href="/catalog" className="block text-center text-sm font-bold text-sky-brand hover:underline">← Продовжити покупки</Link>
        </aside>
      </div>
    </div>
  );
}

import Link from "next/link";
import type { ProductCardData } from "@/lib/catalog";
import { DiscountBadge, Price } from "@/components/ui/Price";
import { ProductImage } from "@/components/ui/ProductImage";
import { StockBadge } from "@/components/ui/StockBadge";
import { AddToCartButton } from "@/components/cart/AddToCartButton";

export function ProductCard({ product }: { product: ProductCardData }) {
  const href = `/product/${product.slug}`;
  return (
    <article className="card group flex flex-col overflow-hidden transition hover:-translate-y-1 hover:shadow-lg">
      <Link href={href} className="relative block overflow-hidden bg-brand-50">
        <ProductImage src={product.images[0]} alt={product.name} className="transition duration-300 group-hover:scale-105" />
        <div className="absolute left-3 top-3 flex gap-2">
          <DiscountBadge price={product.price} oldPrice={product.oldPrice} />
        </div>
      </Link>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-center justify-between text-xs font-semibold text-ink/50">
          <span>{product.category.name}</span>
          <span>Арт. {product.sku}</span>
        </div>
        <h3 className="line-clamp-2 font-bold leading-snug">
          <Link href={href} className="hover:text-sky-brand">{product.name}</Link>
        </h3>
        <p className="text-xs text-ink/60">
          {product.ageMin}+ років · {product.pieces} дет.
        </p>
        <div className="mt-auto space-y-3 pt-2">
          <div className="flex items-end justify-between gap-2">
            <Price price={product.price} oldPrice={product.oldPrice} />
          </div>
          <StockBadge stock={product.stock} />
          <AddToCartButton productId={product.id} disabled={product.stock <= 0} compact />
        </div>
      </div>
    </article>
  );
}

export function ProductGrid({ products }: { products: ProductCardData[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 xl:grid-cols-4">
      {products.map((p) => (
        <ProductCard key={p.id} product={p} />
      ))}
    </div>
  );
}

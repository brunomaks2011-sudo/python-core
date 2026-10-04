import { discountPercent, formatUAH } from "@/lib/money";
import { cn } from "@/lib/utils";

export function Price({ price, oldPrice, size = "md" }: { price: number; oldPrice?: number | null; size?: "md" | "lg" }) {
  const hasDiscount = !!oldPrice && oldPrice > price;
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className={cn("font-black", size === "lg" ? "text-3xl" : "text-lg", hasDiscount && "text-tomato-600")}>
        {formatUAH(price)}
      </span>
      {hasDiscount && (
        <span className={cn("text-ink/50 line-through", size === "lg" ? "text-lg" : "text-sm")}>
          <span className="sr-only">Стара ціна: </span>
          {formatUAH(oldPrice!)}
        </span>
      )}
    </div>
  );
}

export function DiscountBadge({ price, oldPrice }: { price: number; oldPrice?: number | null }) {
  const pct = discountPercent(price, oldPrice);
  if (!pct) return null;
  return <span className="rounded-full bg-tomato-500 px-2.5 py-1 text-xs font-black text-white">−{pct}%</span>;
}

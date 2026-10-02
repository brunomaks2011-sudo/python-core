import { cn } from "@/lib/utils";

export function StockBadge({ stock, className }: { stock: number; className?: string }) {
  const [text, color] =
    stock <= 0
      ? ["Немає в наявності", "bg-ink/10 text-ink/60"]
      : stock <= 5
        ? [`Закінчується: ${stock} шт.`, "bg-brand-100 text-brand-600"]
        : ["В наявності", "bg-emerald-100 text-emerald-700"];
  return <span className={cn("inline-block rounded-full px-2.5 py-1 text-xs font-bold", color, className)}>{text}</span>;
}

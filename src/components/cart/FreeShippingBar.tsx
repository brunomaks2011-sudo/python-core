import { formatUAH } from "@/lib/money";

export function FreeShippingBar({ itemsTotal, threshold }: { itemsTotal: number; threshold: number }) {
  if (threshold <= 0) return null;
  const left = threshold - itemsTotal;
  const pct = Math.min(100, Math.round((itemsTotal / threshold) * 100));
  return (
    <div className="rounded-2xl bg-brand-50 p-3 text-sm">
      <p className="font-bold">
        {left > 0 ? <>До безкоштовної доставки бракує {formatUAH(left)}</> : <>🎉 Доставка Новою Поштою та Укрпоштою — безкоштовна!</>}
      </p>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-white" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

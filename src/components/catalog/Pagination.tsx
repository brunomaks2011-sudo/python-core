import Link from "next/link";
import { cn } from "@/lib/utils";

export function Pagination({ page, pages, hrefFor }: { page: number; pages: number; hrefFor: (p: number) => string }) {
  if (pages <= 1) return null;
  const nums = new Set([1, pages, page - 1, page, page + 1].filter((n) => n >= 1 && n <= pages));
  const sorted = [...nums].sort((a, b) => a - b);
  return (
    <nav aria-label="Сторінки" className="mt-10 flex flex-wrap items-center justify-center gap-2">
      {page > 1 && <Link className="btn-ghost px-4 py-2" href={hrefFor(page - 1)} rel="prev">← Назад</Link>}
      {sorted.map((n, i) => (
        <span key={n} className="flex items-center gap-2">
          {i > 0 && n - sorted[i - 1] > 1 && <span className="text-ink/40">…</span>}
          <Link
            href={hrefFor(n)}
            aria-current={n === page ? "page" : undefined}
            className={cn(
              "flex h-10 min-w-10 items-center justify-center rounded-full px-3 text-sm font-bold",
              n === page ? "bg-ink text-white" : "bg-white hover:bg-brand-100",
            )}
          >
            {n}
          </Link>
        </span>
      ))}
      {page < pages && <Link className="btn-ghost px-4 py-2" href={hrefFor(page + 1)} rel="next">Далі →</Link>}
    </nav>
  );
}

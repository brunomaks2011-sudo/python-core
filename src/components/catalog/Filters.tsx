import Link from "next/link";
import { AGE_OPTIONS, PIECES_OPTIONS, type CatalogQuery } from "@/lib/catalog";

type Category = { slug: string; name: string; _count: { products: number } };

/** Фільтри — звичайна GET-форма: працює без JavaScript, а URL зручно ділитися. */
export function Filters({
  query,
  categories,
  action,
  lockedCategory,
}: {
  query: CatalogQuery;
  categories: Category[];
  action: string;
  lockedCategory?: string;
}) {
  return (
    <form action={action} method="get" className="space-y-6">
      {query.q && <input type="hidden" name="q" value={query.q} />}
      {query.sort !== "popular" && <input type="hidden" name="sort" value={query.sort} />}

      {!lockedCategory && (
        <fieldset>
          <legend className="mb-2 font-black">Серія</legend>
          <div className="space-y-1.5">
            {categories.map((c) => (
              <label key={c.slug} className="flex cursor-pointer items-center gap-2 text-sm">
                <input type="checkbox" name="category" value={c.slug} defaultChecked={query.category.includes(c.slug)} className="h-4 w-4 accent-tomato-500" />
                <span className="flex-1">{c.name}</span>
                <span className="text-xs text-ink/40">{c._count.products}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <fieldset>
        <legend className="mb-2 font-black">Вік</legend>
        <div className="space-y-1.5">
          {Object.entries(AGE_OPTIONS).map(([k, o]) => (
            <label key={k} className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" name="age" value={k} defaultChecked={query.age.includes(k as never)} className="h-4 w-4 accent-tomato-500" />
              {o.label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-2 font-black">Ціна, ₴</legend>
        <div className="flex items-center gap-2">
          <input type="number" name="priceMin" min={0} placeholder="від" defaultValue={query.priceMin} className="input" aria-label="Ціна від" />
          <span>—</span>
          <input type="number" name="priceMax" min={0} placeholder="до" defaultValue={query.priceMax} className="input" aria-label="Ціна до" />
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-2 font-black">Кількість деталей</legend>
        <div className="space-y-1.5">
          {Object.entries(PIECES_OPTIONS).map(([k, o]) => (
            <label key={k} className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" name="pieces" value={k} defaultChecked={query.pieces.includes(k as never)} className="h-4 w-4 accent-tomato-500" />
              {o.label}
            </label>
          ))}
        </div>
      </fieldset>

      <label className="flex cursor-pointer items-center gap-2 text-sm font-bold">
        <input type="checkbox" name="inStock" value="1" defaultChecked={query.inStock} className="h-4 w-4 accent-tomato-500" />
        Лише в наявності
      </label>

      <div className="flex gap-2">
        <button type="submit" className="btn-primary flex-1">Застосувати</button>
        <Link href={action} className="btn-ghost">Скинути</Link>
      </div>
    </form>
  );
}

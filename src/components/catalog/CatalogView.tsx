import { Suspense } from "react";
import { catalogHref, getCategories, searchProducts, type CatalogQuery } from "@/lib/catalog";
import { pluralUk } from "@/lib/utils";
import { Filters } from "./Filters";
import { ProductGrid } from "./ProductCard";
import { SortSelect } from "./SortSelect";
import { Pagination } from "./Pagination";
import { SearchForm } from "./SearchForm";

export async function CatalogView({
  query,
  basePath,
  title,
  description,
  lockedCategory,
  breadcrumbs,
}: {
  query: CatalogQuery;
  basePath: string;
  title: string;
  description?: string | null;
  lockedCategory?: string;
  breadcrumbs: React.ReactNode;
}) {
  const effective = lockedCategory ? { ...query, category: [lockedCategory] } : query;
  const [{ items, total, pages }, categories] = await Promise.all([searchProducts(effective), getCategories()]);
  const page = Math.min(query.page, pages);

  return (
    <div className="container-page py-6">
      {breadcrumbs}
      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black sm:text-4xl">{title}</h1>
          {description && <p className="mt-1 text-ink/70">{description}</p>}
          <p className="mt-1 text-sm text-ink/50">
            Знайдено {total} {pluralUk(total, ["товар", "товари", "товарів"])}
            {query.q && <> за запитом «{query.q}»</>}
          </p>
        </div>
        <div className="flex w-full flex-wrap items-center gap-3 sm:w-auto">
          <SearchForm action={basePath} defaultValue={query.q} />
          <Suspense>
            <SortSelect value={query.sort} />
          </Suspense>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[260px_1fr]">
        <aside>
          <details className="card p-4 lg:hidden">
            <summary className="cursor-pointer font-black">Фільтри</summary>
            <div className="mt-4">
              <Filters query={query} categories={categories} action={basePath} lockedCategory={lockedCategory} />
            </div>
          </details>
          <div className="card sticky top-20 hidden p-5 lg:block">
            <Filters query={query} categories={categories} action={basePath} lockedCategory={lockedCategory} />
          </div>
        </aside>
        <section aria-label="Товари">
          {items.length ? (
            <ProductGrid products={items} />
          ) : (
            <div className="card p-10 text-center">
              <p className="text-xl font-black">Нічого не знайдено 🧱</p>
              <p className="mt-2 text-ink/60">Спробуйте змінити фільтри або пошуковий запит.</p>
            </div>
          )}
          <Pagination page={page} pages={pages} hrefFor={(p) => catalogHref(basePath, query, { page: p > 1 ? p : undefined })} />
        </section>
      </div>
    </div>
  );
}

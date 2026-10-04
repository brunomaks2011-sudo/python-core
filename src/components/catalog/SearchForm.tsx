export function SearchForm({ action = "/catalog", defaultValue, className }: { action?: string; defaultValue?: string; className?: string }) {
  return (
    <form action={action} method="get" role="search" className={className ?? "flex flex-1 sm:w-72 sm:flex-none"}>
      <label className="sr-only" htmlFor={`search-${action}`}>Пошук за назвою або артикулом</label>
      <input
        id={`search-${action}`}
        type="search"
        name="q"
        defaultValue={defaultValue}
        placeholder="Назва або артикул…"
        maxLength={100}
        className="input rounded-r-none"
      />
      <button type="submit" className="rounded-r-xl bg-ink px-4 text-sm font-bold text-white" aria-label="Шукати">🔍</button>
    </form>
  );
}

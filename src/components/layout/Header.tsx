import Link from "next/link";
import { auth } from "@/auth";
import { getCartCount } from "@/lib/cart/server";
import { prisma } from "@/lib/prisma";
import { Logo } from "./Logo";
import { SearchForm } from "@/components/catalog/SearchForm";

export async function Header() {
  const [session, count, categories] = await Promise.all([
    auth(),
    getCartCount(),
    prisma.category.findMany({ orderBy: { sortOrder: "asc" }, select: { slug: true, name: true } }),
  ]);
  const isAdmin = session?.user?.role === "ADMIN";

  return (
    <header className="sticky top-0 z-40 border-b-2 border-ink/5 bg-white/95 backdrop-blur">
      <div className="container-page flex h-16 items-center gap-3 sm:gap-6">
        <Logo />
        <SearchForm className="hidden flex-1 md:flex md:max-w-md" />
        <nav className="ml-auto flex items-center gap-1 text-sm font-bold sm:gap-2" aria-label="Основна навігація">
          <Link href="/catalog" className="hidden rounded-full px-3 py-2 hover:bg-brand-100 sm:block">Каталог</Link>
          {isAdmin && (
            <Link href="/admin" className="hidden rounded-full px-3 py-2 text-sky-brand hover:bg-brand-100 sm:block">Адмінка</Link>
          )}
          <Link
            href={session ? "/account" : "/login"}
            className="flex items-center gap-1 rounded-full px-3 py-2 hover:bg-brand-100"
            aria-label={session ? "Особистий кабінет" : "Увійти"}
          >
            <span aria-hidden>👤</span>
            <span className="hidden sm:inline">{session ? "Кабінет" : "Увійти"}</span>
          </Link>
          <Link href="/cart" className="relative flex items-center gap-1 rounded-full bg-brand-400 px-4 py-2 hover:bg-brand-300" aria-label={`Кошик, товарів: ${count}`}>
            <span aria-hidden>🛒</span>
            <span className="hidden sm:inline">Кошик</span>
            {count > 0 && (
              <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-tomato-500 px-1 text-[11px] font-black text-white">
                {count > 99 ? "99+" : count}
              </span>
            )}
          </Link>
        </nav>
      </div>
      <div className="border-t border-ink/5">
        <div className="container-page pt-2 md:hidden">
          <SearchForm className="flex w-full" />
        </div>
        <nav className="container-page flex gap-1 overflow-x-auto py-1.5 text-sm font-bold [scrollbar-width:none]" aria-label="Серії">
          <Link href="/catalog" className="whitespace-nowrap rounded-full px-3 py-1 hover:bg-brand-100 sm:hidden">Усі</Link>
          {categories.map((c) => (
            <Link key={c.slug} href={`/catalog/${c.slug}`} className="whitespace-nowrap rounded-full px-3 py-1 text-ink/70 hover:bg-brand-100 hover:text-ink">
              {c.name}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}

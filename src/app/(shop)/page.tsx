/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { getCategories, getNewProducts, getPopularProducts } from "@/lib/catalog";
import { ProductGrid } from "@/components/catalog/ProductCard";
import { getShopSettings } from "@/lib/settings";
import { formatUAH } from "@/lib/money";
import { siteConfig, absoluteUrl } from "@/config/site";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [popular, fresh, categories, settings] = await Promise.all([
    getPopularProducts(8),
    getNewProducts(4),
    getCategories(),
    getShopSettings(),
  ]);

  const orgJsonLd = {
    "@context": "https://schema.org",
    "@type": "Store",
    name: siteConfig.name,
    url: siteConfig.url,
    logo: absoluteUrl("/icon.svg"),
    telephone: siteConfig.phone,
    potentialAction: {
      "@type": "SearchAction",
      target: `${siteConfig.url}/catalog?q={search_term_string}`,
      "query-input": "required name=search_term_string",
    },
  };

  return (
    <>
      {/* Банер */}
      <section className="relative overflow-hidden bg-gradient-to-br from-brand-300 via-brand-400 to-brand-500">
        <div aria-hidden className="pointer-events-none absolute inset-0 opacity-20 [background-image:radial-gradient(circle_at_center,#fff_6px,transparent_7px)] [background-size:40px_40px]" />
        <div className="container-page relative grid items-center gap-8 py-12 md:grid-cols-2 md:py-20">
          <div>
            <p className="inline-block -rotate-2 rounded-full bg-white px-4 py-1 text-sm font-black text-tomato-600 shadow">
              Нові набори щотижня
            </p>
            <h1 className="mt-4 text-4xl font-black leading-tight text-ink sm:text-5xl lg:text-6xl">
              Будуй світ <span className="text-white [text-shadow:0_3px_0_#1d2433]">цеглинка</span> за цеглинкою
            </h1>
            <p className="mt-4 max-w-lg text-lg font-semibold text-ink/80">
              Оригінальні конструктори LEGO® для дітей і дорослих. Безкоштовна доставка від {formatUAH(settings.freeShippingThreshold)}.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/catalog" className="btn-primary px-7 py-3 text-base">До каталогу</Link>
              <Link href="/catalog?sort=new" className="btn-ghost px-7 py-3 text-base">Новинки</Link>
            </div>
          </div>
          <div className="relative mx-auto w-full max-w-md">
            <img src="/images/hero.svg" alt="Замок, зібраний з цеглинок" width={800} height={800} className="w-full rotate-3 rounded-[2rem] border-8 border-white shadow-2xl" />
          </div>
        </div>
      </section>

      {/* Переваги */}
      <section className="container-page -mt-6 relative z-10 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["🧱", "Оригінальні набори"],
          ["🚚", "Нова Пошта та Укрпошта"],
          ["💳", "Apple Pay / Google Pay"],
          ["🎁", "Подарункове пакування"],
        ].map(([icon, text]) => (
          <div key={text} className="card flex items-center gap-3 p-4 text-sm font-bold">
            <span className="text-2xl" aria-hidden>{icon}</span>
            {text}
          </div>
        ))}
      </section>

      {/* Категорії */}
      <section className="container-page mt-14">
        <div className="flex items-end justify-between">
          <h2 className="text-3xl font-black">Серії</h2>
          <Link href="/catalog" className="text-sm font-bold text-sky-brand hover:underline">Усі товари →</Link>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {categories.map((c) => (
            <Link key={c.id} href={`/catalog/${c.slug}`} className="card group overflow-hidden text-center transition hover:-translate-y-1 hover:shadow-lg">
              <img src={c.image || "/images/placeholder.svg"} alt="" width={800} height={800} loading="lazy" className="aspect-square w-full object-cover transition group-hover:scale-105" />
              <div className="p-3">
                <p className="font-black">{c.name}</p>
                <p className="text-xs text-ink/50">{c._count.products} наборів</p>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* Популярні */}
      <section className="container-page mt-14">
        <div className="flex items-end justify-between">
          <h2 className="text-3xl font-black">Популярні товари</h2>
          <Link href="/catalog" className="text-sm font-bold text-sky-brand hover:underline">Більше →</Link>
        </div>
        <div className="mt-5">
          <ProductGrid products={popular} />
        </div>
      </section>

      {/* Новинки */}
      <section className="container-page mt-14">
        <div className="flex items-end justify-between">
          <h2 className="text-3xl font-black">Новинки</h2>
          <Link href="/catalog?sort=new" className="text-sm font-bold text-sky-brand hover:underline">Усі новинки →</Link>
        </div>
        <div className="mt-5">
          <ProductGrid products={fresh} />
        </div>
      </section>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(orgJsonLd).replace(/</g, "\\u003c") }} />
    </>
  );
}

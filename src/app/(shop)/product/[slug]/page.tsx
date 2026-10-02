import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { getProductBySlug, getSimilarProducts } from "@/lib/catalog";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { ProductGallery } from "@/components/catalog/ProductGallery";
import { ProductGrid } from "@/components/catalog/ProductCard";
import { DiscountBadge, Price } from "@/components/ui/Price";
import { StockBadge } from "@/components/ui/StockBadge";
import { AddToCartButton } from "@/components/cart/AddToCartButton";
import { absoluteUrl } from "@/config/site";
import { kopecksToUahString } from "@/lib/money";

type Props = { params: Promise<{ slug: string }> };

const getProduct = cache((slug: string) => getProductBySlug(slug));

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const product = await getProduct((await params).slug);
  if (!product) return { title: "Товар не знайдено" };
  const description = product.description.slice(0, 160);
  return {
    title: `${product.name} (${product.sku}) — LEGO® ${product.category.name}`,
    description,
    alternates: { canonical: `/product/${product.slug}` },
    openGraph: {
      type: "website",
      title: product.name,
      description,
      url: `/product/${product.slug}`,
      // Соцмережі не показують SVG, тож для заглушок використовуємо загальне зображення
      images: product.images
        .filter((url) => !url.endsWith(".svg"))
        .slice(0, 1)
        .map((url) => ({ url, alt: product.name }))
        .concat(product.images.some((u) => !u.endsWith(".svg")) ? [] : [{ url: "/og.png", alt: product.name }]),
    },
  };
}

export default async function ProductPage({ params }: Props) {
  const product = await getProduct((await params).slug);
  if (!product) notFound();
  const similar = await getSimilarProducts(product);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    sku: product.sku,
    description: product.description,
    image: product.images.map((i) => absoluteUrl(i)),
    brand: { "@type": "Brand", name: "LEGO" },
    category: product.category.name,
    offers: {
      "@type": "Offer",
      url: absoluteUrl(`/product/${product.slug}`),
      priceCurrency: "UAH",
      price: kopecksToUahString(product.price),
      availability: product.stock > 0 ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
    },
  };

  return (
    <div className="container-page py-6">
      <Breadcrumbs
        items={[
          { name: "Каталог", href: "/catalog" },
          { name: product.category.name, href: `/catalog/${product.category.slug}` },
          { name: product.name },
        ]}
      />
      <div className="mt-6 grid gap-8 lg:grid-cols-2">
        <ProductGallery images={product.images} name={product.name} />
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href={`/catalog/${product.category.slug}`} className="rounded-full bg-sky-brand/10 px-3 py-1 text-xs font-black text-sky-brand">
              {product.category.name}
            </Link>
            <DiscountBadge price={product.price} oldPrice={product.oldPrice} />
          </div>
          <h1 className="mt-3 text-3xl font-black leading-tight sm:text-4xl">{product.name}</h1>
          <p className="mt-1 text-sm text-ink/50">Артикул: {product.sku}</p>

          <div className="mt-5">
            <Price price={product.price} oldPrice={product.oldPrice} size="lg" />
            <StockBadge stock={product.stock} className="mt-2" />
          </div>

          <dl className="mt-6 grid grid-cols-3 gap-3 text-center">
            <div className="card p-3">
              <dt className="text-xs text-ink/50">Деталей</dt>
              <dd className="text-xl font-black">{product.pieces}</dd>
            </div>
            <div className="card p-3">
              <dt className="text-xs text-ink/50">Вік</dt>
              <dd className="text-xl font-black">{product.ageMin}+</dd>
            </div>
            <div className="card p-3">
              <dt className="text-xs text-ink/50">Вага</dt>
              <dd className="text-xl font-black">{(product.weightGrams / 1000).toFixed(1)} кг</dd>
            </div>
          </dl>

          <div className="mt-6 max-w-md">
            <AddToCartButton productId={product.id} disabled={product.stock <= 0} maxQuantity={Math.min(product.stock, 99)} />
          </div>

          <section className="mt-8">
            <h2 className="text-xl font-black">Опис</h2>
            <p className="mt-2 whitespace-pre-line leading-relaxed text-ink/80">{product.description}</p>
          </section>

          <ul className="mt-6 space-y-1 text-sm text-ink/70">
            <li>🚚 Доставка Новою Поштою, Укрпоштою або самовивіз</li>
            <li>💳 Оплата карткою, Apple Pay, Google Pay або при отриманні</li>
          </ul>
        </div>
      </div>

      {similar.length > 0 && (
        <section className="mt-16">
          <h2 className="mb-5 text-2xl font-black">Схожі товари</h2>
          <ProductGrid products={similar} />
        </section>
      )}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
    </div>
  );
}

"use client";

import { useState } from "react";
import { ProductImage } from "@/components/ui/ProductImage";
import { cn } from "@/lib/utils";

export function ProductGallery({ images, name }: { images: string[]; name: string }) {
  const list = images.length ? images : ["/images/placeholder.svg"];
  const [active, setActive] = useState(0);
  return (
    <div className="space-y-3">
      <div className="card overflow-hidden bg-brand-50">
        <ProductImage src={list[active]} alt={`${name} — фото ${active + 1}`} priority />
      </div>
      {list.length > 1 && (
        <div className="grid grid-cols-4 gap-3 sm:grid-cols-5" role="tablist" aria-label="Фото товару">
          {list.map((src, i) => (
            <button
              key={src + i}
              type="button"
              role="tab"
              aria-selected={i === active}
              aria-label={`Фото ${i + 1}`}
              onClick={() => setActive(i)}
              className={cn(
                "overflow-hidden rounded-xl border-2 bg-brand-50 transition",
                i === active ? "border-tomato-500" : "border-transparent opacity-70 hover:opacity-100",
              )}
            >
              <ProductImage src={src} alt="" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

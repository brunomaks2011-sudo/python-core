/* eslint-disable @next/next/no-img-element */
import { cn } from "@/lib/utils";

/** Зображення товару. Для SVG-заглушок і завантажених файлів використовуємо звичайний <img> з lazy-loading. */
export function ProductImage({
  src,
  alt,
  className,
  priority,
}: {
  src?: string | null;
  alt: string;
  className?: string;
  priority?: boolean;
}) {
  return (
    <img
      src={src || "/images/placeholder.svg"}
      alt={alt}
      width={800}
      height={800}
      loading={priority ? "eager" : "lazy"}
      decoding="async"
      className={cn("aspect-square w-full object-cover", className)}
    />
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const links = [
  { href: "/admin", label: "📊 Дашборд" },
  { href: "/admin/orders", label: "📦 Замовлення" },
  { href: "/admin/products", label: "🧱 Товари" },
  { href: "/admin/categories", label: "🗂️ Категорії" },
  { href: "/admin/users", label: "👥 Користувачі" },
  { href: "/admin/settings", label: "⚙️ Налаштування" },
];

export function AdminNav() {
  const path = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto px-2 pb-2 lg:flex-col lg:px-3" aria-label="Адмін-меню">
      {links.map((l) => {
        const active = l.href === "/admin" ? path === "/admin" : path.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={cn("whitespace-nowrap rounded-lg px-3 py-2 text-sm font-bold", active ? "bg-brand-400 text-ink" : "text-white/80 hover:bg-white/10")}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}

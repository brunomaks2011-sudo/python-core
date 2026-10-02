"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const links = [
  { href: "/account", label: "👤 Профіль" },
  { href: "/account/orders", label: "📦 Мої замовлення" },
  { href: "/account/addresses", label: "📍 Адреси доставки" },
];

export function AccountNav() {
  const path = usePathname();
  return (
    <nav className="flex gap-2 overflow-x-auto lg:flex-col" aria-label="Кабінет">
      {links.map((l) => {
        const active = l.href === "/account" ? path === l.href : path.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={cn("whitespace-nowrap rounded-xl px-4 py-2.5 text-sm font-bold", active ? "bg-ink text-white" : "bg-white hover:bg-brand-100")}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}

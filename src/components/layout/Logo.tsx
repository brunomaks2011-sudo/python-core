import Link from "next/link";
import { siteConfig } from "@/config/site";

/** Власний логотип магазину: жовто-синя цеглинка з усмішкою. */
export function LogoMark({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <rect x="10" y="4" width="16" height="10" rx="4" fill="#2463eb" />
      <rect x="38" y="4" width="16" height="10" rx="4" fill="#2463eb" />
      <rect x="4" y="12" width="56" height="44" rx="12" fill="#ffc233" />
      <rect x="4" y="46" width="56" height="10" rx="5" fill="#f5a300" />
      <circle cx="23" cy="30" r="4" fill="#1d2433" />
      <circle cx="41" cy="30" r="4" fill="#1d2433" />
      <path d="M22 39 q10 8 20 0" stroke="#1d2433" strokeWidth="4" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2" aria-label={`${siteConfig.name} — на головну`}>
      <LogoMark />
      <span className="text-xl font-black tracking-tight text-ink">
        Цеглин<span className="text-sky-brand">ка</span>
      </span>
    </Link>
  );
}

import Link from "next/link";
import { siteConfig } from "@/config/site";
import { LogoMark } from "./Logo";

export function Footer() {
  return (
    <footer className="mt-16 border-t-4 border-brand-400 bg-ink text-white/80">
      <div className="container-page grid gap-8 py-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <div className="flex items-center gap-2 text-lg font-black text-white">
            <LogoMark className="h-8 w-8" /> {siteConfig.name}
          </div>
          <p className="mt-3 text-sm">{siteConfig.shortDescription}. Оригінальні набори, швидка доставка та чесні ціни.</p>
        </div>
        <div>
          <h2 className="mb-3 font-bold text-white">Покупцям</h2>
          <ul className="space-y-2 text-sm">
            <li><Link className="hover:text-brand-300" href="/catalog">Каталог</Link></li>
            <li><Link className="hover:text-brand-300" href="/cart">Кошик</Link></li>
            <li><Link className="hover:text-brand-300" href="/account">Особистий кабінет</Link></li>
          </ul>
        </div>
        <div>
          <h2 className="mb-3 font-bold text-white">Доставка та оплата</h2>
          <ul className="space-y-2 text-sm">
            <li>Нова Пошта: відділення, поштомат, кур&apos;єр</li>
            <li>Укрпошта</li>
            <li>Самовивіз — безкоштовно</li>
            <li>Картка, Apple Pay, Google Pay або при отриманні</li>
          </ul>
        </div>
        <div>
          <h2 className="mb-3 font-bold text-white">Контакти</h2>
          <ul className="space-y-2 text-sm">
            <li><a className="hover:text-brand-300" href={`tel:${siteConfig.phone.replace(/\s/g, "")}`}>{siteConfig.phone}</a></li>
            <li><a className="hover:text-brand-300" href={`mailto:${siteConfig.email}`}>{siteConfig.email}</a></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10 py-4 text-center text-xs text-white/50">
        © {new Date().getFullYear()} {siteConfig.name}. LEGO® є торговою маркою групи компаній LEGO, яка не спонсорує та не
        підтримує цей сайт.
      </div>
    </footer>
  );
}

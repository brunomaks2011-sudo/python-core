import Link from "next/link";
import { Logo } from "./Logo";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b-2 border-ink/5 bg-white/90 backdrop-blur">
      <div className="container-page flex h-16 items-center gap-4">
        <Logo />
        <nav className="ml-auto flex items-center gap-4 text-sm font-bold">
          <Link href="/catalog">Каталог</Link>
          <Link href="/cart">Кошик</Link>
        </nav>
      </div>
    </header>
  );
}

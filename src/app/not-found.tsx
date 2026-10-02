import Link from "next/link";
import { LogoMark } from "@/components/layout/Logo";

export const metadata = { title: "Сторінку не знайдено" };

export default function NotFound() {
  return (
    <main className="container-page flex flex-1 flex-col items-center justify-center py-20 text-center">
      <LogoMark className="h-24 w-24 -rotate-12" />
      <p className="mt-6 text-7xl font-black text-brand-500">404</p>
      <h1 className="mt-2 text-2xl font-black">Ой! Тут бракує деталі</h1>
      <p className="mt-2 max-w-md text-ink/70">
        Сторінку, яку ви шукаєте, не знайдено. Можливо, її перемістили або видалили.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <Link href="/" className="btn-primary">На головну</Link>
        <Link href="/catalog" className="btn-ghost">До каталогу</Link>
      </div>
    </main>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ForbiddenError, requireAdmin } from "@/lib/auth-guards";
import { LogoMark } from "@/components/layout/Logo";
import { AdminNav } from "@/components/admin/AdminNav";
import { logoutAction } from "@/app/actions/auth";

export const metadata: Metadata = { title: { default: "Адмін-панель", template: "%s | Адмін" }, robots: { index: false, follow: false } };

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  let admin;
  try {
    admin = await requireAdmin();
  } catch (e) {
    if (e instanceof ForbiddenError) notFound();
    throw e;
  }
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside className="bg-ink text-white lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:shrink-0">
        <div className="flex items-center justify-between gap-2 p-4 lg:block">
          <Link href="/admin" className="flex items-center gap-2 font-black">
            <LogoMark className="h-8 w-8" /> Адмін-панель
          </Link>
          <p className="truncate text-xs text-white/50 lg:mt-1">{admin.email}</p>
        </div>
        <AdminNav />
        <div className="hidden space-y-2 p-4 lg:block">
          <Link href="/" className="block text-sm text-white/60 hover:text-white">← На сайт</Link>
          <form action={logoutAction}>
            <button className="text-sm text-white/60 hover:text-white">Вийти</button>
          </form>
        </div>
      </aside>
      <main className="min-w-0 flex-1 bg-[#f6f7fb] p-4 sm:p-6 lg:p-8">{children}</main>
    </div>
  );
}

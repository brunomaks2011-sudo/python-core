import { requireUser } from "@/lib/auth-guards";
import { AccountNav } from "@/components/account/AccountNav";
import { logoutAction } from "@/app/actions/auth";

export const metadata = { title: "Особистий кабінет", robots: { index: false } };

export default async function AccountLayout({ children }: { children: React.ReactNode }) {
  const user = await requireUser();
  return (
    <div className="container-page py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-black">Привіт, {user.name.split(" ")[0]}! 👋</h1>
          <p className="text-sm text-ink/60">{user.email}</p>
        </div>
        <form action={logoutAction}>
          <button className="btn-ghost">Вийти</button>
        </form>
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-[220px_1fr]">
        <AccountNav />
        <div>{children}</div>
      </div>
    </div>
  );
}

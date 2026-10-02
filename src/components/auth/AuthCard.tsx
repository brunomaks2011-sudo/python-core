import { LogoMark } from "@/components/layout/Logo";

export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="container-page flex justify-center py-12">
      <div className="card w-full max-w-md p-6 sm:p-8">
        <LogoMark className="mx-auto h-14 w-14" />
        <h1 className="mt-3 text-center text-2xl font-black">{title}</h1>
        {subtitle && <p className="mt-1 text-center text-sm text-ink/60">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
    </div>
  );
}

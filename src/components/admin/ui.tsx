import { cn } from "@/lib/utils";

export function PageTitle({ children, actions }: { children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-black sm:text-3xl">{children}</h1>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, children, className }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-2xl bg-white p-4 shadow-sm sm:p-5", className)}>
      {title && <h2 className="mb-3 text-lg font-black">{title}</h2>}
      {children}
    </section>
  );
}

export function Table({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-2xl bg-white shadow-sm">
      <table className="w-full min-w-[640px] text-left text-sm [&_td]:px-4 [&_td]:py-3 [&_th]:px-4 [&_th]:py-3 [&_th]:text-xs [&_th]:font-black [&_th]:uppercase [&_th]:text-ink/50 [&_tbody_tr]:border-t [&_tbody_tr]:border-ink/5 [&_tbody_tr:hover]:bg-brand-50/50">
        {children}
      </table>
    </div>
  );
}

"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { SORT_OPTIONS } from "@/lib/catalog";

export function SortSelect({ value }: { value: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  return (
    <label className="flex items-center gap-2 text-sm font-semibold">
      <span className="hidden sm:inline">Сортування:</span>
      <select
        className="input w-auto py-2"
        value={value}
        onChange={(e) => {
          const next = new URLSearchParams(params.toString());
          if (e.target.value === "popular") next.delete("sort");
          else next.set("sort", e.target.value);
          next.delete("page");
          const qs = next.toString();
          router.push(qs ? `${pathname}?${qs}` : pathname);
        }}
      >
        {Object.entries(SORT_OPTIONS).map(([k, label]) => (
          <option key={k} value={k}>{label}</option>
        ))}
      </select>
    </label>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export type Picked = { name: string; ref: string | null };

type City = { ref: string; name: string; area: string };
type Warehouse = { ref: string; name: string; number: string };

function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Пошук міста через API Нової Пошти. Без API-ключа — звичайне текстове поле. */
export function NpCityPicker({ id, configured, value, onChange }: { id: string; configured: boolean; value: Picked; onChange: (v: Picked) => void }) {
  const [query, setQuery] = useState(value.name);
  const [items, setItems] = useState<City[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounced = useDebounced(query);
  const skipNext = useRef(false);

  useEffect(() => setQuery(value.name), [value.name]);

  useEffect(() => {
    if (!configured || skipNext.current) {
      skipNext.current = false;
      return;
    }
    if (debounced.trim().length < 2) {
      setItems([]);
      return;
    }
    const ctrl = new AbortController();
    fetch(`/api/delivery/np/cities?q=${encodeURIComponent(debounced)}`, { signal: ctrl.signal })
      .then((r) => r.json())
      .then((d) => {
        setItems(d.items ?? []);
        setError(d.error ?? null);
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, [debounced, configured]);

  if (!configured) {
    return (
      <>
        <input id={id} className="input" value={value.name} onChange={(e) => onChange({ name: e.target.value, ref: null })} placeholder="Наприклад: Львів" />
        <p className="mt-1 text-xs text-ink/50">Вартість розраховується за фіксованим тарифом.</p>
      </>
    );
  }

  return (
    <div className="relative">
      <input
        id={id}
        className="input"
        role="combobox"
        aria-expanded={open && items.length > 0}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder="Почніть вводити назву міста…"
        value={query}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          // Поки місто не вибране зі списку — точного ref немає (рахується резервний тариф)
          onChange({ name: e.target.value, ref: null });
        }}
      />
      {error && <p className="mt-1 text-xs text-tomato-600">{error}. Можна ввести місто вручну.</p>}
      {open && items.length > 0 && (
        <ul role="listbox" className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-xl border-2 border-ink/10 bg-white shadow-lg">
          {items.map((c) => (
            <li key={c.ref}>
              <button
                type="button"
                role="option"
                aria-selected={value.ref === c.ref}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-brand-50"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  skipNext.current = true;
                  setQuery(c.name);
                  onChange({ name: c.name, ref: c.ref });
                  setOpen(false);
                }}
              >
                <span className="font-semibold">{c.name}</span> <span className="text-ink/50">{c.area} обл.</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Вибір відділення/поштомату для обраного міста. */
export function NpWarehousePicker({
  id,
  configured,
  cityRef,
  kind,
  value,
  onChange,
}: {
  id: string;
  configured: boolean;
  cityRef: string | null;
  kind: "warehouse" | "postomat";
  value: Picked;
  onChange: (v: Picked) => void;
}) {
  const [filter, setFilter] = useState("");
  const [items, setItems] = useState<Warehouse[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const debounced = useDebounced(filter);

  useEffect(() => {
    if (!configured || !cityRef) {
      setItems([]);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    fetch(`/api/delivery/np/warehouses?cityRef=${cityRef}&type=${kind}&q=${encodeURIComponent(debounced)}`, { signal: ctrl.signal })
      .then((r) => r.json())
      .then((d) => {
        setItems(d.items ?? []);
        setFailed(!!d.error);
      })
      .catch(() => {})
      .finally(() => !ctrl.signal.aborted && setLoading(false));
    return () => ctrl.abort();
  }, [configured, cityRef, kind, debounced]);

  // Без API або при збої — ручне введення
  if (!configured || failed || !cityRef) {
    return (
      <>
        <input
          id={id}
          className="input"
          value={value.name}
          placeholder={kind === "postomat" ? "Номер поштомату, напр. Поштомат №5123" : "Номер відділення, напр. Відділення №12"}
          onChange={(e) => onChange({ name: e.target.value, ref: null })}
        />
        {configured && !cityRef && <p className="mt-1 text-xs text-ink/50">Оберіть місто зі списку, щоб побачити відділення.</p>}
      </>
    );
  }

  return (
    <div className="space-y-2">
      <input className="input" placeholder="Пошук за номером або адресою…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Фільтр відділень" />
      <select
        id={id}
        className={cn("input", loading && "opacity-60")}
        value={value.ref ?? ""}
        onChange={(e) => {
          const w = items.find((i) => i.ref === e.target.value);
          onChange(w ? { name: w.name, ref: w.ref } : { name: "", ref: null });
        }}
      >
        <option value="">{loading ? "Завантаження…" : items.length ? "Оберіть зі списку" : "Нічого не знайдено"}</option>
        {value.ref && !items.some((i) => i.ref === value.ref) && <option value={value.ref}>{value.name}</option>}
        {items.map((w) => (
          <option key={w.ref} value={w.ref}>{w.name}</option>
        ))}
      </select>
    </div>
  );
}

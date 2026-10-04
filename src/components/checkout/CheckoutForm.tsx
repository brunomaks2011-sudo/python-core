"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import Link from "next/link";
import { submitCheckout } from "@/app/actions/checkout";
import { formatUAH } from "@/lib/money";
import { cn } from "@/lib/utils";
import { NpCityPicker, NpWarehousePicker, type Picked } from "./NpPickers";

type DeliveryMethod = "NP_WAREHOUSE" | "NP_POSTOMAT" | "NP_COURIER" | "UKRPOSHTA" | "PICKUP";
type PaymentMethod = "LIQPAY" | "COD";

type Quote = { cost: number; baseCost: number; free: boolean; source: "api" | "fallback" | "flat"; note?: string };

export type SavedAddress = {
  id: string;
  label: string;
  deliveryMethod: DeliveryMethod;
  city: string;
  cityRef: string | null;
  warehouse: string | null;
  warehouseRef: string | null;
  street: string | null;
  building: string | null;
  apartment: string | null;
  postalCode: string | null;
};

type Props = {
  items: { id: string; name: string; quantity: number; price: number }[];
  itemsTotal: number;
  freeShippingThreshold: number;
  liqpayAvailable: boolean;
  liqpaySandbox: boolean;
  npConfigured: boolean;
  pickupAddress: string;
  defaults: { name: string; email: string; phone: string };
  savedAddresses: SavedAddress[];
  isLoggedIn: boolean;
};

const METHODS: { id: DeliveryMethod; title: string; hint: string }[] = [
  { id: "NP_WAREHOUSE", title: "Нова Пошта — відділення", hint: "1–3 дні" },
  { id: "NP_POSTOMAT", title: "Нова Пошта — поштомат", hint: "1–3 дні, до 30 кг" },
  { id: "NP_COURIER", title: "Нова Пошта — кур'єр", hint: "доставка до дверей" },
  { id: "UKRPOSHTA", title: "Укрпошта", hint: "3–5 днів, фіксований тариф" },
  { id: "PICKUP", title: "Самовивіз", hint: "безкоштовно" },
];

const STEPS = ["Контакти", "Доставка", "Оплата", "Перевірка"] as const;

export function CheckoutForm(props: Props) {
  const [step, setStep] = useState(0);
  const [contact, setContact] = useState(props.defaults);
  const [method, setMethod] = useState<DeliveryMethod>("NP_WAREHOUSE");
  const [city, setCity] = useState<Picked>({ name: "", ref: null });
  const [warehouse, setWarehouse] = useState<Picked>({ name: "", ref: null });
  const [addr, setAddr] = useState({ street: "", building: "", apartment: "", postalCode: "" });
  const [payment, setPayment] = useState<PaymentMethod>(props.liqpayAvailable ? "LIQPAY" : "COD");
  const [comment, setComment] = useState("");
  const [saveAddress, setSaveAddress] = useState(props.isLoggedIn);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [submitting, startSubmit] = useTransition();

  const isNp = method.startsWith("NP_");

  // Перерахунок вартості доставки в реальному часі
  useEffect(() => {
    const ctrl = new AbortController();
    setQuoteLoading(true);
    const timer = setTimeout(() => {
      fetch("/api/delivery/quote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method, cityRef: isNp ? city.ref : null }),
        signal: ctrl.signal,
      })
        .then((r) => r.json())
        .then((d) => d.quote && setQuote(d.quote))
        .catch(() => {})
        .finally(() => !ctrl.signal.aborted && setQuoteLoading(false));
    }, 250);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [method, city.ref, isNp]);

  const deliveryPayload = useMemo(() => {
    switch (method) {
      case "NP_WAREHOUSE":
      case "NP_POSTOMAT":
        return { method, city: city.name, cityRef: city.ref ?? undefined, warehouse: warehouse.name, warehouseRef: warehouse.ref ?? undefined };
      case "NP_COURIER":
        return { method, city: city.name, cityRef: city.ref ?? undefined, street: addr.street, building: addr.building, apartment: addr.apartment || undefined };
      case "UKRPOSHTA":
        return { method, city: city.name, postalCode: addr.postalCode, street: addr.street || undefined, building: addr.building || undefined };
      case "PICKUP":
        return { method };
    }
  }, [method, city, warehouse, addr]);

  const applySaved = (a: SavedAddress) => {
    setMethod(a.deliveryMethod);
    setCity({ name: a.city, ref: a.cityRef });
    setWarehouse({ name: a.warehouse ?? "", ref: a.warehouseRef });
    setAddr({ street: a.street ?? "", building: a.building ?? "", apartment: a.apartment ?? "", postalCode: a.postalCode ?? "" });
    setSaveAddress(false);
  };

  // Мінімальна перевірка на клієнті (повна — на сервері)
  const validateStep = (s: number): boolean => {
    const e: Record<string, string> = {};
    if (s === 0) {
      if (contact.name.trim().length < 2) e["contact.name"] = "Вкажіть ім'я та прізвище";
      if (!/^\+?3?8?0\d{9}$/.test(contact.phone.replace(/[\s()-]/g, ""))) e["contact.phone"] = "Телефон у форматі +380XXXXXXXXX";
      if (!/^\S+@\S+\.\S+$/.test(contact.email)) e["contact.email"] = "Некоректний email";
    }
    if (s === 1 && method !== "PICKUP") {
      if (city.name.trim().length < 2) e["delivery.city"] = "Вкажіть місто";
      if ((method === "NP_WAREHOUSE" || method === "NP_POSTOMAT") && !warehouse.name.trim())
        e["delivery.warehouse"] = method === "NP_POSTOMAT" ? "Оберіть поштомат" : "Оберіть відділення";
      if (method === "NP_COURIER") {
        if (addr.street.trim().length < 2) e["delivery.street"] = "Вкажіть вулицю";
        if (!addr.building.trim()) e["delivery.building"] = "Вкажіть будинок";
      }
      if (method === "UKRPOSHTA" && !/^\d{5}$/.test(addr.postalCode)) e["delivery.postalCode"] = "Індекс — 5 цифр";
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const next = () => {
    if (validateStep(step)) setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const submit = () =>
    startSubmit(async () => {
      setFormError(null);
      const res = await submitCheckout({ contact, delivery: deliveryPayload, paymentMethod: payment, comment: comment || undefined, saveAddress });
      if (res.ok) {
        window.location.href = res.redirectUrl;
        return;
      }
      setFormError(res.error);
      if (res.fieldErrors) {
        setErrors(res.fieldErrors);
        const keys = Object.keys(res.fieldErrors);
        if (keys.some((k) => k.startsWith("contact"))) setStep(0);
        else if (keys.some((k) => k.startsWith("delivery"))) setStep(1);
      }
    });

  const deliverySummary = (() => {
    const street = [addr.street, addr.building].filter(Boolean).join(" ");
    switch (method) {
      case "PICKUP":
        return props.pickupAddress;
      case "NP_WAREHOUSE":
      case "NP_POSTOMAT":
        return [city.name, warehouse.name].filter(Boolean).join(", ");
      case "NP_COURIER":
        return [city.name, street, addr.apartment && `кв. ${addr.apartment}`].filter(Boolean).join(", ");
      case "UKRPOSHTA":
        return [addr.postalCode, city.name, street].filter(Boolean).join(", ");
    }
  })();

  const deliveryCost = method === "PICKUP" ? 0 : (quote?.cost ?? null);
  const total = props.itemsTotal + (deliveryCost ?? 0);

  const err = (k: string) => errors[k] && <p className="field-error">{errors[k]}</p>;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div>
        {/* Кроки */}
        <ol className="mb-6 flex gap-2 overflow-x-auto text-sm font-bold">
          {STEPS.map((s, i) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => i < step && setStep(i)}
                disabled={i > step}
                className={cn(
                  "flex items-center gap-2 whitespace-nowrap rounded-full px-3 py-1.5",
                  i === step ? "bg-ink text-white" : i < step ? "bg-emerald-100 text-emerald-700" : "bg-white text-ink/40",
                )}
              >
                <span>{i < step ? "✓" : i + 1}</span> {s}
              </button>
            </li>
          ))}
        </ol>

        <div className="card p-5 sm:p-6">
          {step === 0 && (
            <section className="space-y-4">
              <h2 className="text-xl font-black">Контактні дані</h2>
              {!props.isLoggedIn && (
                <p className="rounded-xl bg-sky-brand/5 p-3 text-sm">
                  Оформлення доступне без реєстрації. Маєте акаунт?{" "}
                  <Link href="/login?callbackUrl=/checkout" className="font-bold text-sky-brand underline">Увійдіть</Link>
                </p>
              )}
              <div>
                <label className="label" htmlFor="c-name">Ім&apos;я та прізвище</label>
                <input id="c-name" className="input" autoComplete="name" value={contact.name} onChange={(e) => setContact({ ...contact, name: e.target.value })} />
                {err("contact.name")}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="label" htmlFor="c-phone">Телефон</label>
                  <input id="c-phone" className="input" type="tel" autoComplete="tel" placeholder="+380 67 123 45 67" value={contact.phone} onChange={(e) => setContact({ ...contact, phone: e.target.value })} />
                  {err("contact.phone")}
                </div>
                <div>
                  <label className="label" htmlFor="c-email">Email</label>
                  <input id="c-email" className="input" type="email" autoComplete="email" value={contact.email} onChange={(e) => setContact({ ...contact, email: e.target.value })} />
                  {err("contact.email")}
                </div>
              </div>
            </section>
          )}

          {step === 1 && (
            <section className="space-y-4">
              <h2 className="text-xl font-black">Доставка</h2>
              {props.savedAddresses.length > 0 && (
                <div>
                  <p className="label">Збережені адреси</p>
                  <div className="flex flex-wrap gap-2">
                    {props.savedAddresses.map((a) => (
                      <button key={a.id} type="button" onClick={() => applySaved(a)} className="btn-ghost px-3 py-1.5 text-xs">
                        {a.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <fieldset className="grid gap-2 sm:grid-cols-2">
                <legend className="sr-only">Спосіб доставки</legend>
                {METHODS.map((m) => (
                  <label
                    key={m.id}
                    className={cn(
                      "flex cursor-pointer items-start gap-3 rounded-2xl border-2 p-3 transition",
                      method === m.id ? "border-tomato-500 bg-tomato-500/5" : "border-ink/10 hover:border-ink/30",
                    )}
                  >
                    <input type="radio" name="delivery" className="mt-1 accent-tomato-500" checked={method === m.id} onChange={() => { setMethod(m.id); setWarehouse({ name: "", ref: null }); }} />
                    <span>
                      <span className="block font-bold">{m.title}</span>
                      <span className="text-xs text-ink/60">{m.hint}</span>
                    </span>
                  </label>
                ))}
              </fieldset>

              {method !== "PICKUP" && (
                <div>
                  <label className="label" htmlFor="d-city">Місто</label>
                  {isNp ? (
                    <NpCityPicker id="d-city" configured={props.npConfigured} value={city} onChange={(c) => { setCity(c); setWarehouse({ name: "", ref: null }); }} />
                  ) : (
                    <input id="d-city" className="input" value={city.name} onChange={(e) => setCity({ name: e.target.value, ref: null })} />
                  )}
                  {err("delivery.city")}
                </div>
              )}

              {(method === "NP_WAREHOUSE" || method === "NP_POSTOMAT") && (
                <div>
                  <label className="label" htmlFor="d-wh">{method === "NP_POSTOMAT" ? "Поштомат" : "Відділення"}</label>
                  <NpWarehousePicker
                    id="d-wh"
                    configured={props.npConfigured}
                    cityRef={city.ref}
                    kind={method === "NP_POSTOMAT" ? "postomat" : "warehouse"}
                    value={warehouse}
                    onChange={setWarehouse}
                  />
                  {err("delivery.warehouse")}
                </div>
              )}

              {method === "NP_COURIER" && (
                <div className="grid gap-4 sm:grid-cols-[1fr_120px_120px]">
                  <div>
                    <label className="label" htmlFor="d-street">Вулиця</label>
                    <input id="d-street" className="input" autoComplete="address-line1" value={addr.street} onChange={(e) => setAddr({ ...addr, street: e.target.value })} />
                    {err("delivery.street")}
                  </div>
                  <div>
                    <label className="label" htmlFor="d-building">Будинок</label>
                    <input id="d-building" className="input" value={addr.building} onChange={(e) => setAddr({ ...addr, building: e.target.value })} />
                    {err("delivery.building")}
                  </div>
                  <div>
                    <label className="label" htmlFor="d-apt">Квартира</label>
                    <input id="d-apt" className="input" value={addr.apartment} onChange={(e) => setAddr({ ...addr, apartment: e.target.value })} />
                  </div>
                </div>
              )}

              {method === "UKRPOSHTA" && (
                <div className="grid gap-4 sm:grid-cols-[140px_1fr_120px]">
                  <div>
                    <label className="label" htmlFor="d-zip">Індекс</label>
                    <input id="d-zip" className="input" inputMode="numeric" maxLength={5} autoComplete="postal-code" value={addr.postalCode} onChange={(e) => setAddr({ ...addr, postalCode: e.target.value.replace(/\D/g, "") })} />
                    {err("delivery.postalCode")}
                  </div>
                  <div>
                    <label className="label" htmlFor="d-ustreet">Вулиця (необов&apos;язково)</label>
                    <input id="d-ustreet" className="input" value={addr.street} onChange={(e) => setAddr({ ...addr, street: e.target.value })} />
                  </div>
                  <div>
                    <label className="label" htmlFor="d-ubuilding">Будинок</label>
                    <input id="d-ubuilding" className="input" value={addr.building} onChange={(e) => setAddr({ ...addr, building: e.target.value })} />
                  </div>
                </div>
              )}

              {method === "PICKUP" && (
                <p className="rounded-xl bg-brand-50 p-3 text-sm">
                  📍 {props.pickupAddress}. Ми зателефонуємо, коли замовлення буде готове.
                </p>
              )}

              {props.isLoggedIn && method !== "PICKUP" && (
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" className="accent-tomato-500" checked={saveAddress} onChange={(e) => setSaveAddress(e.target.checked)} />
                  Зберегти адресу в особистому кабінеті
                </label>
              )}
            </section>
          )}

          {step === 2 && (
            <section className="space-y-4">
              <h2 className="text-xl font-black">Оплата</h2>
              <div className="grid gap-2">
                <label className={cn("flex items-start gap-3 rounded-2xl border-2 p-3", !props.liqpayAvailable ? "cursor-not-allowed opacity-50" : "cursor-pointer", payment === "LIQPAY" ? "border-tomato-500 bg-tomato-500/5" : "border-ink/10")}>
                  <input type="radio" name="payment" className="mt-1 accent-tomato-500" disabled={!props.liqpayAvailable} checked={payment === "LIQPAY"} onChange={() => setPayment("LIQPAY")} />
                  <span>
                    <span className="block font-bold">Карткою онлайн</span>
                    <span className="text-xs text-ink/60">
                      Visa / Mastercard будь-якого українського банку, Apple Pay, Google Pay — через LiqPay.
                      {!props.liqpayAvailable && " Тимчасово недоступно."}
                      {props.liqpayAvailable && props.liqpaySandbox && " (тестовий режим)"}
                    </span>
                  </span>
                </label>
                <label className={cn("flex cursor-pointer items-start gap-3 rounded-2xl border-2 p-3", payment === "COD" ? "border-tomato-500 bg-tomato-500/5" : "border-ink/10")}>
                  <input type="radio" name="payment" className="mt-1 accent-tomato-500" checked={payment === "COD"} onChange={() => setPayment("COD")} />
                  <span>
                    <span className="block font-bold">{method === "PICKUP" ? "Оплата при самовивозі" : "Оплата при отриманні (накладений платіж)"}</span>
                    <span className="text-xs text-ink/60">
                      {method === "PICKUP" ? "Готівкою або карткою в магазині" : "Оплата у відділенні. Перевізник стягує комісію за переказ коштів."}
                    </span>
                  </span>
                </label>
              </div>
              <div>
                <label className="label" htmlFor="comment">Коментар до замовлення</label>
                <textarea id="comment" className="input min-h-24" maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Наприклад: подарункове пакування" />
              </div>
            </section>
          )}

          {step === 3 && (
            <section className="space-y-4 text-sm">
              <h2 className="text-xl font-black">Перевірте замовлення</h2>
              <dl className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-brand-50 p-3">
                  <dt className="text-xs font-bold text-ink/50">Отримувач</dt>
                  <dd className="font-semibold">{contact.name}<br />{contact.phone}<br />{contact.email}</dd>
                </div>
                <div className="rounded-xl bg-brand-50 p-3">
                  <dt className="text-xs font-bold text-ink/50">Доставка</dt>
                  <dd className="font-semibold">
                    {METHODS.find((m) => m.id === method)?.title}
                    <br />
                    {deliverySummary}
                  </dd>
                </div>
                <div className="rounded-xl bg-brand-50 p-3 sm:col-span-2">
                  <dt className="text-xs font-bold text-ink/50">Оплата</dt>
                  <dd className="font-semibold">{payment === "LIQPAY" ? "Карткою онлайн (LiqPay)" : "При отриманні"}</dd>
                </div>
              </dl>
              {comment && <p className="text-ink/70">Коментар: {comment}</p>}
              <p className="text-xs text-ink/60">Натискаючи «Підтвердити замовлення», ви погоджуєтеся з умовами продажу та обробкою персональних даних.</p>
            </section>
          )}

          {formError && <p role="alert" className="mt-4 rounded-xl bg-tomato-500/10 p-3 text-sm font-bold text-tomato-600">{formError}</p>}

          <div className="mt-6 flex justify-between gap-3">
            {step > 0 ? (
              <button type="button" className="btn-ghost" onClick={() => setStep((s) => s - 1)} disabled={submitting}>← Назад</button>
            ) : (
              <Link href="/cart" className="btn-ghost">← До кошика</Link>
            )}
            {step < STEPS.length - 1 ? (
              <button type="button" className="btn-primary" onClick={next}>Далі →</button>
            ) : (
              <button type="button" className="btn-primary px-8" onClick={submit} disabled={submitting}>
                {submitting ? "Оформлюємо…" : payment === "LIQPAY" ? "Підтвердити та оплатити" : "Підтвердити замовлення"}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Підсумок */}
      <aside className="card h-fit p-5 lg:sticky lg:top-24">
        <h2 className="text-lg font-black">Ваше замовлення</h2>
        <ul className="mt-3 space-y-2 text-sm">
          {props.items.map((i) => (
            <li key={i.id} className="flex justify-between gap-3">
              <span className="text-ink/80">{i.name} × {i.quantity}</span>
              <span className="whitespace-nowrap font-semibold">{formatUAH(i.price * i.quantity)}</span>
            </li>
          ))}
        </ul>
        <div className="mt-4 space-y-2 border-t-2 border-dashed border-ink/10 pt-4 text-sm">
          <div className="flex justify-between"><span>Товари</span><span className="font-semibold">{formatUAH(props.itemsTotal)}</span></div>
          <div className="flex justify-between">
            <span>Доставка</span>
            <span className="font-semibold" aria-live="polite">
              {quoteLoading ? "…" : deliveryCost === null ? "—" : deliveryCost === 0 ? <span className="text-emerald-700">безкоштовно</span> : formatUAH(deliveryCost)}
            </span>
          </div>
          {quote?.free && quote.baseCost > 0 && method !== "PICKUP" && (
            <p className="text-xs text-emerald-700">Безкоштовна доставка від {formatUAH(props.freeShippingThreshold)} 🎉</p>
          )}
          {quote?.note && method !== "PICKUP" && <p className="text-xs text-ink/50">{quote.note}</p>}
          {payment === "COD" && method !== "PICKUP" && <p className="text-xs text-ink/50">+ комісія перевізника за накладений платіж</p>}
        </div>
        <div className="mt-4 flex items-baseline justify-between border-t-2 border-ink/10 pt-4">
          <span className="font-bold">До сплати</span>
          <span className="text-2xl font-black">{formatUAH(total)}</span>
        </div>
      </aside>
    </div>
  );
}

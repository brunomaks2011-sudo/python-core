import { NextResponse } from "next/server";
import { getWarehouses, isNovaPoshtaConfigured } from "@/lib/delivery/novaposhta";

export async function GET(req: Request) {
  if (!isNovaPoshtaConfigured()) return NextResponse.json({ configured: false, items: [] });
  const sp = new URL(req.url).searchParams;
  const cityRef = sp.get("cityRef") ?? "";
  if (!/^[0-9a-f-]{36}$/i.test(cityRef)) return NextResponse.json({ error: "Некоректне місто" }, { status: 400 });
  const kind = sp.get("type") === "postomat" ? "postomat" : "warehouse";
  try {
    return NextResponse.json({ configured: true, items: await getWarehouses(cityRef, kind, (sp.get("q") ?? "").slice(0, 60)) });
  } catch (e) {
    console.warn("[np] warehouses:", (e as Error).message);
    return NextResponse.json({ configured: true, error: "Сервіс Нової Пошти недоступний", items: [] }, { status: 502 });
  }
}

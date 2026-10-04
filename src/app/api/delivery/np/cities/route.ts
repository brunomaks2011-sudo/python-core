import { NextResponse } from "next/server";
import { isNovaPoshtaConfigured, searchCities } from "@/lib/delivery/novaposhta";

export async function GET(req: Request) {
  if (!isNovaPoshtaConfigured()) return NextResponse.json({ configured: false, items: [] });
  const q = (new URL(req.url).searchParams.get("q") ?? "").slice(0, 60);
  try {
    return NextResponse.json({ configured: true, items: await searchCities(q) });
  } catch (e) {
    console.warn("[np] cities:", (e as Error).message);
    return NextResponse.json({ configured: true, error: "Сервіс Нової Пошти недоступний", items: [] }, { status: 502 });
  }
}

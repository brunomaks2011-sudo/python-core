import { NextResponse } from "next/server";
import { getPaymentProvider, InvalidSignatureError } from "@/lib/payments";
import { applyPaymentResult } from "@/lib/orders/payment";

/**
 * Webhook платіжної системи (LiqPay надсилає POST з полями data та signature).
 * Статус замовлення змінюється ЛИШЕ після успішної перевірки підпису.
 */
export async function POST(req: Request, { params }: { params: Promise<{ provider: string }> }) {
  const provider = getPaymentProvider((await params).provider);
  if (!provider || !provider.isConfigured()) return NextResponse.json({ error: "unknown provider" }, { status: 404 });

  let body: Record<string, string> = {};
  const type = req.headers.get("content-type") ?? "";
  try {
    if (type.includes("application/json")) body = await req.json();
    else body = Object.fromEntries([...(await req.formData()).entries()].map(([k, v]) => [k, String(v)]));
  } catch {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }

  try {
    const cb = provider.parseCallback(body);
    const result = await applyPaymentResult(cb);
    console.info(`[payment:${provider.id}] ${cb.externalId} ${cb.providerStatus} → ${result}`);
    return NextResponse.json({ ok: true, result });
  } catch (e) {
    if (e instanceof InvalidSignatureError) {
      console.warn(`[payment:${provider.id}] invalid signature`);
      return NextResponse.json({ error: "invalid signature" }, { status: 400 });
    }
    console.error(`[payment:${provider.id}] callback error`, e);
    return NextResponse.json({ error: "server error" }, { status: 500 });
  }
}

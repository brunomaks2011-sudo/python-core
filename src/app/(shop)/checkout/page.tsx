import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { prisma } from "@/lib/prisma";
import { getCart } from "@/lib/cart/server";
import { getShopSettings, pickupAddress } from "@/lib/settings";
import { getOnlinePaymentProvider, isSandbox } from "@/lib/payments";
import { isNovaPoshtaConfigured } from "@/lib/delivery/novaposhta";
import { DELIVERY_METHODS } from "@/lib/delivery/methods";
import { CheckoutForm, type SavedAddress } from "@/components/checkout/CheckoutForm";

export const metadata: Metadata = { title: "Оформлення замовлення", robots: { index: false } };

export default async function CheckoutPage() {
  const [cart, settings, session] = await Promise.all([getCart(), getShopSettings(), auth()]);
  if (cart.items.length === 0 || cart.hasUnavailable) redirect("/cart");

  const user = session?.user?.id
    ? await prisma.user.findUnique({
        where: { id: session.user.id },
        include: { addresses: { orderBy: [{ isDefault: "desc" }, { createdAt: "desc" }] } },
      })
    : null;

  const savedAddresses: SavedAddress[] = (user?.addresses ?? []).map((a) => ({
    id: a.id,
    label: a.label || `${DELIVERY_METHODS[a.deliveryMethod].short}: ${a.city}${a.warehouse ? `, ${a.warehouse.slice(0, 30)}` : ""}`,
    deliveryMethod: a.deliveryMethod,
    city: a.city,
    cityRef: a.cityRef,
    warehouse: a.warehouse,
    warehouseRef: a.warehouseRef,
    street: a.street,
    building: a.building,
    apartment: a.apartment,
    postalCode: a.postalCode,
  }));

  return (
    <div className="container-page py-8">
      <h1 className="mb-6 text-3xl font-black">Оформлення замовлення</h1>
      <CheckoutForm
        items={cart.items.map((i) => ({ id: i.id, name: i.product.name, quantity: i.quantity, price: i.product.price }))}
        itemsTotal={cart.itemsTotal}
        freeShippingThreshold={settings.freeShippingThreshold}
        liqpayAvailable={!!getOnlinePaymentProvider()}
        liqpaySandbox={isSandbox()}
        npConfigured={isNovaPoshtaConfigured()}
        pickupAddress={pickupAddress()}
        defaults={{ name: user?.name ?? "", email: user?.email ?? "", phone: user?.phone ?? "" }}
        savedAddresses={savedAddresses}
        isLoggedIn={!!user}
      />
    </div>
  );
}

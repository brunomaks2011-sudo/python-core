import { prisma } from "@/lib/prisma";
import { requireUser } from "@/lib/auth-guards";
import { DELIVERY_METHODS, describeDelivery } from "@/lib/delivery/methods";
import { AddressForm } from "@/components/account/AddressForm";
import { deleteAddressAction, setDefaultAddressAction } from "@/app/actions/account";

export default async function AddressesPage() {
  const user = await requireUser("/account/addresses");
  const addresses = await prisma.address.findMany({ where: { userId: user.id }, orderBy: [{ isDefault: "desc" }, { createdAt: "desc" }] });

  return (
    <div className="space-y-6">
      {addresses.length > 0 ? (
        <ul className="grid gap-3 md:grid-cols-2">
          {addresses.map((a) => (
            <li key={a.id} className="card p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-black">
                    {a.label || DELIVERY_METHODS[a.deliveryMethod].short}
                    {a.isDefault && <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">основна</span>}
                  </p>
                  <p className="text-sm text-ink/70">{DELIVERY_METHODS[a.deliveryMethod].label}</p>
                  <p className="text-sm">{describeDelivery(a.deliveryMethod, a)}</p>
                  <p className="text-xs text-ink/50">{a.recipientName}, {a.recipientPhone}</p>
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                {!a.isDefault && (
                  <form action={setDefaultAddressAction}>
                    <input type="hidden" name="id" value={a.id} />
                    <button className="btn-ghost px-3 py-1.5 text-xs">Зробити основною</button>
                  </form>
                )}
                <form action={deleteAddressAction}>
                  <input type="hidden" name="id" value={a.id} />
                  <button className="btn-ghost px-3 py-1.5 text-xs text-tomato-600">Видалити</button>
                </form>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="card p-6 text-ink/60">Збережених адрес ще немає. Додайте адресу тут або під час оформлення замовлення.</p>
      )}
      <AddressForm defaultName={user.name} defaultPhone={user.phone ?? ""} />
    </div>
  );
}

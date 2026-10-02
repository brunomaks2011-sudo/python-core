import { requireAdmin } from "@/lib/auth-guards";
import { getShopSettings } from "@/lib/settings";
import { PageTitle, Panel } from "@/components/admin/ui";
import { SettingsForm } from "@/components/admin/SettingsForm";
import { getOnlinePaymentProvider, isSandbox } from "@/lib/payments";
import { isNovaPoshtaConfigured } from "@/lib/delivery/novaposhta";

export const metadata = { title: "Налаштування" };

export default async function AdminSettingsPage() {
  await requireAdmin();
  const settings = await getShopSettings();
  const integrations = [
    { name: "LiqPay", ok: !!getOnlinePaymentProvider(), note: getOnlinePaymentProvider() ? (isSandbox() ? "sandbox (тестовий режим)" : "бойовий режим") : "ключі не задані — доступна лише оплата при отриманні" },
    { name: "Нова Пошта API", ok: isNovaPoshtaConfigured(), note: isNovaPoshtaConfigured() ? "розрахунок за тарифами НП" : "ключ не задано — резервні тарифи, ручне введення відділення" },
    { name: "SMTP", ok: !!process.env.SMTP_HOST, note: process.env.SMTP_HOST ? "листи надсилаються" : "листи виводяться в лог сервера" },
    { name: "Vercel Blob", ok: !!process.env.BLOB_READ_WRITE_TOKEN, note: process.env.BLOB_READ_WRITE_TOKEN ? "зображення у Vercel Blob" : "зображення на локальному диску (UPLOAD_DIR)" },
  ];
  return (
    <>
      <PageTitle>Налаштування</PageTitle>
      <div className="grid gap-6 xl:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-black">Доставка</h2>
          <SettingsForm settings={settings} />
        </div>
        <Panel title="Інтеграції (змінні середовища)">
          <ul className="space-y-3 text-sm">
            {integrations.map((i) => (
              <li key={i.name} className="flex gap-3">
                <span aria-hidden>{i.ok ? "🟢" : "⚪"}</span>
                <span><span className="font-bold">{i.name}</span> — {i.note}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-xs text-ink/50">Ключі змінюються лише через змінні середовища (.env / налаштування хостингу), не через адмінку.</p>
        </Panel>
      </div>
    </>
  );
}

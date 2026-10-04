import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { AuthCard } from "@/components/auth/AuthCard";
import { LoginForm } from "@/components/auth/LoginForm";

export const metadata: Metadata = { title: "Вхід", robots: { index: false } };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ callbackUrl?: string }> }) {
  const { callbackUrl } = await searchParams;
  if (await auth()) redirect("/account");
  return (
    <AuthCard title="Вхід до кабінету" subtitle="Історія замовлень, збережені адреси та швидке оформлення">
      <LoginForm callbackUrl={callbackUrl} />
    </AuthCard>
  );
}

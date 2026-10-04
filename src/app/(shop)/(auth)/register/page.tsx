import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { AuthCard } from "@/components/auth/AuthCard";
import { RegisterForm } from "@/components/auth/RegisterForm";

export const metadata: Metadata = { title: "Реєстрація", robots: { index: false } };

export default async function RegisterPage({ searchParams }: { searchParams: Promise<{ callbackUrl?: string }> }) {
  const { callbackUrl } = await searchParams;
  if (await auth()) redirect("/account");
  return (
    <AuthCard title="Реєстрація" subtitle="Кошик збережеться і на інших пристроях">
      <RegisterForm callbackUrl={callbackUrl} />
    </AuthCard>
  );
}

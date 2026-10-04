import type { Metadata } from "next";
import Link from "next/link";
import { AuthCard } from "@/components/auth/AuthCard";
import { ResetPasswordForm } from "@/components/auth/PasswordForms";

export const metadata: Metadata = { title: "Новий пароль", robots: { index: false } };

export default async function ResetPasswordPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  return (
    <AuthCard title="Новий пароль">
      {token ? (
        <ResetPasswordForm token={token} />
      ) : (
        <p className="text-center text-sm">
          Посилання неповне. <Link href="/forgot-password" className="font-bold text-sky-brand">Запросіть нове</Link>.
        </p>
      )}
    </AuthCard>
  );
}

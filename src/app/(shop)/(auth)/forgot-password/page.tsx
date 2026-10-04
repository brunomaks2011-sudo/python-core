import type { Metadata } from "next";
import { AuthCard } from "@/components/auth/AuthCard";
import { ForgotPasswordForm } from "@/components/auth/PasswordForms";

export const metadata: Metadata = { title: "Відновлення пароля", robots: { index: false } };

export default function ForgotPasswordPage() {
  return (
    <AuthCard title="Відновлення пароля" subtitle="Вкажіть email — ми надішлемо посилання для зміни пароля">
      <ForgotPasswordForm />
    </AuthCard>
  );
}

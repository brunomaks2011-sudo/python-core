import { requireUser } from "@/lib/auth-guards";
import { ChangePasswordForm, ProfileForm } from "@/components/account/ProfileForms";

export default async function AccountPage() {
  const user = await requireUser();
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <ProfileForm name={user.name} phone={user.phone ?? ""} email={user.email} />
      <ChangePasswordForm />
    </div>
  );
}

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ._prompts import ask, ask_email, ask_password


class Command(BaseCommand):
    help = "Змінити пошту, ім'я та пароль власника магазину. Усе питає сама, пароль не видно під час введення."

    def handle(self, *args, **opts):
        User = get_user_model()
        owners = list(User.objects.filter(is_superuser=True).order_by("pk"))
        if not owners:
            raise CommandError("Власника ще немає. Створіть його: python manage.py createsuperuser")
        try:
            user = owners[0]
            if len(owners) > 1:
                for i, u in enumerate(owners, start=1):
                    self.stdout.write(f"  {i}. {u.email}")
                choice = ask("Номер акаунта, який змінити", "1")
                if not choice.isdigit() or not 1 <= int(choice) <= len(owners):
                    raise CommandError("Немає такого номера")
                user = owners[int(choice) - 1]
            self.stdout.write(f"Зараз вхід: {user.email}. Enter — залишити як є.")
            user.email = ask_email("Нова пошта", user.email,
                                   taken=lambda e: User.objects.filter(email__iexact=e).exclude(pk=user.pk).exists())
            user.first_name = ask("Ваше ім'я (видно на мітках товарів)", user.first_name)
            password = ask_password(user, allow_keep=True)
        except (KeyboardInterrupt, EOFError):
            raise CommandError("Скасовано, нічого не змінено")
        if password:
            user.set_password(password)
        user.is_active = user.is_staff = True
        user.save()
        self.stdout.write(self.style.SUCCESS(
            f"Готово. Вхід: {user.email}" + (" з новим паролем" if password else " (пароль той самий)")))

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ._prompts import ask, ask_email, ask_password


class Command(BaseCommand):
    help = ("Створити акаунт другому адміністратору (доступ до панелі, свої товари й продажі в статистиці). "
            "Усе питає сама, пароль не видно під час введення.")

    def handle(self, *args, **opts):
        User = get_user_model()
        try:
            email = ask_email("Пошта нового адміністратора")
            user = User.objects.filter(email__iexact=email).first()
            if user is not None:
                answer = ask(f"Акаунт {user.email} уже є. Дати йому доступ до панелі й новий пароль? (так/ні)", "так")
                if answer.lower() not in ("так", "т", "да", "д", "yes", "y"):
                    raise CommandError("Скасовано, нічого не змінено")
            name = ask("Його ім'я (видно на мітках товарів)", user.first_name if user else "")
            password = ask_password(user)
        except (KeyboardInterrupt, EOFError):
            raise CommandError("Скасовано, нічого не змінено")
        if user is None:
            user = User.objects.create_user(email, password, first_name=name, is_staff=True)
        else:
            user.first_name = name
            user.set_password(password)
            user.is_staff = user.is_active = True
            user.save()
        self.stdout.write(self.style.SUCCESS(f"Готово. {name or user.email} входить у панель з поштою {user.email}"))

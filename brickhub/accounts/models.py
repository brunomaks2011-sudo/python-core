from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Потрібна електронна пошта")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra.get("is_staff") or not extra.get("is_superuser"):
            raise ValueError("Суперкористувач повинен мати is_staff=True та is_superuser=True")
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class User(AbstractUser):
    """Shop customer / staff account. Logs in with e-mail."""

    username = None
    email = models.EmailField("Електронна пошта", unique=True)
    phone = models.CharField("Телефон", max_length=20, blank=True)
    # Default delivery details, pre-filled at checkout.
    city = models.CharField("Місто", max_length=120, blank=True)
    city_ref = models.CharField(max_length=64, blank=True)
    np_warehouse = models.CharField("Відділення / поштомат Нової пошти", max_length=255, blank=True)
    np_warehouse_ref = models.CharField(max_length=64, blank=True)
    address = models.CharField("Адреса", max_length=255, blank=True)
    postal_code = models.CharField("Поштовий індекс", max_length=10, blank=True)
    marketing_opt_in = models.BooleanField("Отримувати новини та знижки", default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "користувач"
        verbose_name_plural = "користувачі"
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_ci_unique")]

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

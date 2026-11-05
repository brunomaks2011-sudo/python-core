from django import forms
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.core.cache import cache

from core.utils import normalize_phone

User = get_user_model()

LOCK_ATTEMPTS = 8
LOCK_SECONDS = 15 * 60


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(label="Пароль", strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="Мінімум 8 символів, не лише цифри")
    password2 = forms.CharField(label="Повторіть пароль", strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    agree = forms.BooleanField(label="Погоджуюся з умовами використання та політикою конфіденційності",
                               error_messages={"required": "Потрібна ваша згода"})

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "marketing_opt_in"]
        labels = {"first_name": "Ім'я", "last_name": "Прізвище"}
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email", "autocapitalize": "none"}),
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "placeholder": "+380"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Акаунт із цією поштою вже існує. Увійдіть або відновіть пароль.")
        return email

    def clean_phone(self):
        raw = self.cleaned_data.get("phone", "")
        if not raw:
            return ""
        phone = normalize_phone(raw)
        if not phone:
            raise forms.ValidationError("Вкажіть український номер, напр. +380 67 123 45 67")
        return phone

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Паролі не збігаються")
        if p1:
            user = User(email=data.get("email", ""), first_name=data.get("first_name", ""))
            try:
                password_validation.validate_password(p1, user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    email = forms.EmailField(label="Електронна пошта",
                             widget=forms.EmailInput(attrs={"autocomplete": "email", "autocapitalize": "none",
                                                            "autofocus": True}))
    password = forms.CharField(label="Пароль", strip=False,
                               widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    remember = forms.BooleanField(label="Запам'ятати мене", required=False, initial=True)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def _key(self, email):
        ip = self.request.META.get("REMOTE_ADDR", "") if self.request else ""
        return f"login-fail:{ip}:{email}"

    def clean(self):
        data = super().clean()
        email, password = (data.get("email") or "").lower(), data.get("password")
        if not email or not password:
            return data
        key = self._key(email)
        if cache.get(key, 0) >= LOCK_ATTEMPTS:
            raise forms.ValidationError("Забагато невдалих спроб. Спробуйте через 15 хвилин або відновіть пароль.")
        self.user = authenticate(self.request, email=email, password=password)
        if self.user is None:
            cache.set(key, cache.get(key, 0) + 1, LOCK_SECONDS)
            raise forms.ValidationError("Невірна пошта або пароль.")
        cache.delete(key)
        return data


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "city", "np_warehouse", "address", "postal_code",
                  "marketing_opt_in"]
        labels = {"first_name": "Ім'я", "last_name": "Прізвище"}
        widgets = {"phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"})}

    def clean_phone(self):
        raw = self.cleaned_data.get("phone", "")
        if not raw:
            return ""
        phone = normalize_phone(raw)
        if not phone:
            raise forms.ValidationError("Вкажіть український номер, напр. +380 67 123 45 67")
        return phone


class EmailChangeForm(forms.Form):
    email = forms.EmailField(label="Нова електронна пошта")
    password = forms.CharField(label="Поточний пароль", widget=forms.PasswordInput)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Ця пошта вже використовується")
        return email

    def clean_password(self):
        pw = self.cleaned_data["password"]
        if not self.user.check_password(pw):
            raise forms.ValidationError("Невірний пароль")
        return pw

from django import forms

from core.utils import normalize_phone

from .models import Order
from .payments import card_payments_enabled


class CheckoutForm(forms.Form):
    first_name = forms.CharField(label="Ім'я", max_length=80,
                                 widget=forms.TextInput(attrs={"autocomplete": "given-name"}))
    last_name = forms.CharField(label="Прізвище", max_length=80,
                                widget=forms.TextInput(attrs={"autocomplete": "family-name"}))
    phone = forms.CharField(label="Телефон", max_length=20, widget=forms.TextInput(
        attrs={"autocomplete": "tel", "type": "tel", "inputmode": "tel", "placeholder": "+380 __ ___ __ __"}))
    email = forms.EmailField(label="Електронна пошта", widget=forms.EmailInput(
        attrs={"autocomplete": "email", "autocapitalize": "none"}))
    delivery_method = forms.ChoiceField(label="Спосіб доставки", choices=Order.DELIVERY_METHODS,
                                        initial=Order.DELIVERY_NP_WAREHOUSE, widget=forms.RadioSelect)
    city = forms.CharField(label="Місто / населений пункт", max_length=160, widget=forms.TextInput(
        attrs={"autocomplete": "address-level2", "placeholder": "Почніть вводити назву"}))
    city_ref = forms.CharField(required=False, widget=forms.HiddenInput)
    np_warehouse = forms.CharField(label="Відділення або поштомат", max_length=255, required=False,
                                   widget=forms.TextInput(attrs={"placeholder": "Напр. Відділення №1 або номер"}))
    np_warehouse_ref = forms.CharField(required=False, widget=forms.HiddenInput)
    address = forms.CharField(label="Адреса (вулиця, будинок, квартира)", max_length=255, required=False,
                              widget=forms.TextInput(attrs={"autocomplete": "street-address"}))
    postal_code = forms.CharField(label="Поштовий індекс", max_length=10, required=False, widget=forms.TextInput(
        attrs={"inputmode": "numeric", "autocomplete": "postal-code", "pattern": "[0-9]{5}"}))
    payment_method = forms.ChoiceField(label="Спосіб оплати", choices=Order.PAYMENT_METHODS,
                                       initial=Order.PAYMENT_COD, widget=forms.RadioSelect)
    comment = forms.CharField(label="Коментар до замовлення", required=False, max_length=2000,
                              widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Побажання щодо доставки тощо"}))
    create_account = forms.BooleanField(label="Створити акаунт для відстеження замовлень", required=False)
    password = forms.CharField(label="Пароль для акаунта", required=False, min_length=8,
                               widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    agree = forms.BooleanField(label="Погоджуюся з умовами використання та політикою конфіденційності",
                               error_messages={"required": "Потрібна ваша згода"})

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not phone:
            raise forms.ValidationError("Вкажіть український номер, напр. +380 67 123 45 67")
        return phone

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_payment_method(self):
        method = self.cleaned_data["payment_method"]
        if method == Order.PAYMENT_CARD and not card_payments_enabled():
            raise forms.ValidationError("Онлайн-оплата карткою поки недоступна. Оберіть накладений платіж.")
        return method

    def clean(self):
        data = super().clean()
        method = data.get("delivery_method")
        if method in (Order.DELIVERY_NP_WAREHOUSE, Order.DELIVERY_NP_POSTOMAT) and not data.get("np_warehouse"):
            self.add_error("np_warehouse", "Вкажіть відділення або поштомат Нової пошти")
        if method in (Order.DELIVERY_NP_COURIER, Order.DELIVERY_UKRPOSHTA) and not data.get("address"):
            self.add_error("address", "Вкажіть адресу доставки")
        if method == Order.DELIVERY_UKRPOSHTA:
            code = (data.get("postal_code") or "").strip()
            if not (code.isdigit() and len(code) == 5):
                self.add_error("postal_code", "Індекс складається з 5 цифр")
        if data.get("create_account") and not data.get("password"):
            self.add_error("password", "Вкажіть пароль (мінімум 8 символів)")
        return data


class TrackForm(forms.Form):
    number = forms.CharField(label="Номер замовлення", max_length=20,
                             widget=forms.TextInput(attrs={"placeholder": "BH26110001", "autocapitalize": "characters"}))
    contact = forms.CharField(label="Телефон або e-mail із замовлення", max_length=120)

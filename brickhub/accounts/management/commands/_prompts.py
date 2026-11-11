"""Questions in the console for the account commands (the password is typed hidden, twice)."""
import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


def ask(text: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    return input(f"{text}{hint}: ").strip() or default


def ask_email(text: str, default: str = "", taken=None) -> str:
    while True:
        email = ask(text, default).lower()
        try:
            validate_email(email)
        except ValidationError:
            print("  Це не схоже на e-mail, спробуйте ще раз.")
            continue
        if taken is not None and taken(email):
            print("  Ця пошта вже зайнята іншим акаунтом.")
            continue
        return email


def ask_password(user=None, allow_keep: bool = False) -> str | None:
    while True:
        first = getpass.getpass("Пароль (символи не показуються)" + (", Enter — залишити старий" if allow_keep else "")
                                + ": ")
        if not first and allow_keep:
            return None
        second = getpass.getpass("Ще раз той самий пароль: ")
        if first != second:
            print("  Паролі не збігаються, спробуйте ще раз.")
            continue
        try:
            validate_password(first, user)
        except ValidationError as e:
            for message in e.messages:
                print("  " + message)
            continue
        return first

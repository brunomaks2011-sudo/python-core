"""Django settings for the BRICK HUB shop.

All secrets and environment specific values come from environment variables
(or a local ``.env`` file, see ``.env.example``).  Nothing secret is stored in
the repository.
"""
from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines, existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] in ('"', "'") and value[1:].find(value[0]) != -1:
            value = value[1:1 + value[1:].find(value[0])]  # quoted value: keep everything inside the quotes
        else:
            value = value.split(" #", 1)[0].split("\t#", 1)[0].strip()  # drop inline comments
        os.environ.setdefault(key.strip(), value)


_load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-change-me"  # noqa: S105 - only used with DEBUG=1
    else:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY (or DJANGO_DEBUG=1 for local development).")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
if DEBUG:
    ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    "core",
    "accounts",
    "catalog",
    "cart",
    "orders",
    "panel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.shop",
                "cart.context_processors.cart",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(env("DJANGO_DB_CONN_MAX_AGE", "60")),
    )
}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    # WAL + immediate transactions keep SQLite reliable with concurrent requests.
    DATABASES["default"].setdefault("OPTIONS", {}).update(
        {"init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;", "transaction_mode": "IMMEDIATE"}
    )
    DATABASES["default"]["CONN_MAX_AGE"] = 0

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "core:home"

LANGUAGE_CODE = "uk"
TIME_ZONE = "Europe/Kyiv"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
# Product photos are served by Django too, so they show up even when the web server has no /media/ mapping
# (e.g. PythonAnywhere without a "Static files" row). Set 0 when nginx & co. serve /media/ themselves.
SERVE_MEDIA = env_bool("DJANGO_SERVE_MEDIA", True)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30 if not DEBUG else 0

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "brickhub",
        "TIMEOUT": 300,
    }
}

# Uploads: product photos and bulk import files (CSV / XLSX with thousands of rows).
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", False)
    SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)
    if env_bool("DJANGO_BEHIND_PROXY", True):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# E-mail: console in development, SMTP when EMAIL_HOST is set.
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "BRICK HUB <noreply@brickhub.ua>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO" if not DEBUG else "WARNING"},
    "loggers": {
        "brickhub": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Shop settings
# ---------------------------------------------------------------------------
SHOP = {
    "NAME": env("SHOP_NAME", "BRICK HUB"),
    "TAGLINE": "Набори, деталі та мініфігурки LEGO®",
    "PHONE": env("SHOP_PHONE", ""),
    "EMAIL": env("SHOP_EMAIL", ""),
    "ADDRESS": env("SHOP_ADDRESS", ""),
    "WORK_HOURS": env("SHOP_WORK_HOURS", "Пн–Пт 9:00–19:00, Сб 10:00–16:00"),
    "SITE_URL": env("SHOP_SITE_URL", "http://localhost:8000"),
    # Orders at or above this sum ship for free (the shop pays the carrier). 0 disables it.
    "FREE_DELIVERY_FROM": int(env("SHOP_FREE_DELIVERY_FROM", "2500")),
    "ORDER_NOTIFY_EMAILS": env_list("SHOP_ORDER_NOTIFY_EMAILS"),
    "LOW_STOCK_THRESHOLD": int(env("SHOP_LOW_STOCK_THRESHOLD", "3")),
}

# Integrations. Each one is switched on only when its credentials are present;
# without them the checkout never pretends that a payment or a shipment succeeded.
NOVA_POSHTA_API_KEY = env("NOVA_POSHTA_API_KEY")
NOVA_POSHTA_API_URL = env("NOVA_POSHTA_API_URL", "https://api.novaposhta.ua/v2.0/json/")
UKRPOSHTA_BEARER_TOKEN = env("UKRPOSHTA_BEARER_TOKEN")
LIQPAY_PUBLIC_KEY = env("LIQPAY_PUBLIC_KEY")
LIQPAY_PRIVATE_KEY = env("LIQPAY_PRIVATE_KEY")
LIQPAY_SANDBOX = env_bool("LIQPAY_SANDBOX", True)

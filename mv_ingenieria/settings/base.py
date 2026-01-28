import os
from datetime import date  # por si luego usas TWO_FACTOR_ENFORCE_DATE
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 3 niveles por /settings/
load_dotenv(os.getenv("ENV_FILE", BASE_DIR / ".env")) # opcional


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-key")
DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

ROOT_URLCONF = "mv_ingenieria.urls"
WSGI_APPLICATION = "mv_ingenieria.wsgi.application"
ASGI_APPLICATION = "mv_ingenieria.asgi.application"


# -----------------------------------------------------------------------------
# Apps
# -----------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    

    # Seguridad
    "axes",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",

    # Proyecto
    "common",
    "core",
    "usuarios",
    "finanzas_comercial",
]


# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    # OTP + Axes
    "django_otp.middleware.OTPMiddleware",
    "axes.middleware.AxesMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # Reglas propias
    # "common.middleware.Enforce2FAMiddleware",  # si lo usas, va antes de Require2FA
    "common.middleware.Require2FAMiddleware",
    "common.middleware.SecurityHeadersMiddleware",
]


# -----------------------------------------------------------------------------
# Templates
# -----------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.menu_context",
            ],
        },
    }
]


# -----------------------------------------------------------------------------
# DB
# -----------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)}


# -----------------------------------------------------------------------------
# Auth / Axes
# -----------------------------------------------------------------------------
AUTH_USER_MODEL = "usuarios.User"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "usuarios:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "usuarios:login"

AXES_FAILURE_LIMIT = int(os.getenv("AXES_FAILURE_LIMIT", "6"))
AXES_COOLOFF_TIME = int(os.getenv("AXES_COOLOFF_TIME", "1"))
AXES_LOCKOUT_TEMPLATE = None

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True


# -----------------------------------------------------------------------------
# i18n
# -----------------------------------------------------------------------------
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True


# -----------------------------------------------------------------------------
# Static / Media
# -----------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# -----------------------------------------------------------------------------
# Wasabi (opcional)
# -----------------------------------------------------------------------------
USE_WASABI = env_bool("USE_WASABI", False)

if USE_WASABI:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_STORAGE_BUCKET_NAME = os.getenv("WASABI_BUCKET_NAME", "")
    AWS_ACCESS_KEY_ID = os.getenv("WASABI_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.getenv("WASABI_SECRET_ACCESS_KEY", "")
    AWS_S3_ENDPOINT_URL = os.getenv("WASABI_ENDPOINT_URL", "")
    AWS_S3_REGION_NAME = os.getenv("WASABI_REGION", "us-east-1")
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    AWS_S3_FILE_OVERWRITE = False


# -----------------------------------------------------------------------------
# Seguridad común (prod/dev ajusta en overrides)
# -----------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# -----------------------------------------------------------------------------
# 2FA / Dispositivos de confianza
# -----------------------------------------------------------------------------
TRUSTED_DEVICE_DAYS = int(os.getenv("TRUSTED_DEVICE_DAYS", "90"))
TRUSTED_DEVICE_COOKIE_NAME = os.getenv("TRUSTED_DEVICE_COOKIE_NAME", "mv_td")
TRUSTED_DEVICE_COOKIE_SAMESITE = os.getenv("TRUSTED_DEVICE_COOKIE_SAMESITE", "Lax")

# En base NO definimos cookie secure (lo define dev/prod)
# TRUSTED_DEVICE_COOKIE_SECURE = ...

# (Opcional) Enforce 2FA por fecha desde env: "YYYY-MM-DD"
_enforce = (os.getenv("TWO_FACTOR_ENFORCE_DATE") or "").strip()
TWO_FACTOR_ENFORCE_DATE = None

if _enforce:
    try:
        y, m, d = _enforce.split("-")
        TWO_FACTOR_ENFORCE_DATE = date(int(y), int(m), int(d))
    except Exception:
        TWO_FACTOR_ENFORCE_DATE = None
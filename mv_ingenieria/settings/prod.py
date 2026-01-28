# mv_ingenieria/settings/prod.py
from .base import *  # noqa

DEBUG = False

# Render / proxy https
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

TRUSTED_DEVICE_COOKIE_SECURE = True

# --- FIX Render hosts/CSRF ---
# Si no configuraste env vars en Render, base.py deja localhost/127.0.0.1
# y eso provoca 400 DisallowedHost. En prod forzamos defaults para Render.
if ALLOWED_HOSTS == ["localhost", "127.0.0.1"]:
    ALLOWED_HOSTS = ["app-ingenieriamv.onrender.com", ".onrender.com"]

if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = ["https://app-ingenieriamv.onrender.com", "https://*.onrender.com"]

USE_X_FORWARDED_HOST = True
# ----------------------------

# HSTS (déjalo 0 al inicio y luego lo subes)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

# (Opcional) Enforce 2FA por fecha desde env: "YYYY-MM-DD"
_enforce = (os.getenv("TWO_FACTOR_ENFORCE_DATE") or "").strip()
if _enforce:
    try:
        y, m, d = _enforce.split("-")
        TWO_FACTOR_ENFORCE_DATE = date(int(y), int(m), int(d))
    except Exception:
        pass
from .base import *  # noqa

DEBUG = False

# Render / proxy https
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

TRUSTED_DEVICE_COOKIE_SECURE = True

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
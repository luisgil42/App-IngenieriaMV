# settings/dev.py
import os

from .base import *  # noqa

DEBUG = True

# local sin https
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

TRUSTED_DEVICE_COOKIE_SECURE = False

# en local, HSTS apagado
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False


from datetime import date

_enforce = (os.getenv("TWO_FACTOR_ENFORCE_DATE") or "").strip()
if _enforce:
    try:
        y, m, d = _enforce.split("-")
        TWO_FACTOR_ENFORCE_DATE = date(int(y), int(m), int(d))
    except Exception:
        pass
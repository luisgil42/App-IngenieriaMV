# mv_ingenieria/settings/dev.py
from .base import *

# -----------------------------------------------------------------------------
# DEV
# -----------------------------------------------------------------------------
DEBUG = True

# 🔥 Desactivar Axes COMPLETAMENTE en desarrollo
AXES_ENABLED = False

# 🔥 Quitar backend de Axes
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# 🔥 Quitar middleware de Axes
MIDDLEWARE = [
    m for m in MIDDLEWARE
    if not m.startswith("axes.")
]

# -----------------------------------------------------------------------------
# Seguridad (en DEV NO usar HTTPS ni HSTS)
# -----------------------------------------------------------------------------
SECURE_SSL_REDIRECT = False

SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
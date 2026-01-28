from .base import *

DEBUG = True

# En dev conviene NO usar HTTPS ni HSTS
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# En dev normalmente quieres ver media local si NO usas Wasabi
# (si quieres Wasabi en dev, déjalo con USE_WASABI=1 en .env)
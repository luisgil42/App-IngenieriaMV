# finanzas_comercial/apps.py
from django.apps import AppConfig


class FinanzasComercialConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finanzas_comercial"
    verbose_name = "Finanzas Comercial"

    def ready(self):
        # conecta señales
        from . import signals  # noqa
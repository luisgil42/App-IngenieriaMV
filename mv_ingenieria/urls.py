from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),

    # ✅ Core con namespace "core"
    path("", include(("core.urls", "core"), namespace="core")),

    # ✅ Usuarios con namespace "usuarios"
    path("usuarios/", include(("usuarios.urls", "usuarios"), namespace="usuarios")),

    # ✅ Finanzas Comercial con namespace "finanzas_comercial"
    path("finanzas-comercial/", include(("finanzas_comercial.urls", "finanzas_comercial"), namespace="finanzas_comercial")),
]

# ✅ Solo si quieres servir MEDIA local cuando DEBUG=True (si usas Wasabi da igual)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
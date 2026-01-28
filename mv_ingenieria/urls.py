from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("usuarios/", include("usuarios.urls")),
    path("finanzas-comercial/", include("finanzas_comercial.urls")),
]
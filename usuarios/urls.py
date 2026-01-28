from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("usuarios/", views.user_list, name="user_list"),
    path("usuarios/nuevo/", views.user_create, name="user_create"),
    path("usuarios/<int:pk>/editar/", views.user_edit, name="user_edit"),

    path("roles/", views.role_list, name="role_list"),
    path("roles/nuevo/", views.role_create, name="role_create"),
    path("roles/<int:pk>/editar/", views.role_edit, name="role_edit"),

    # 2FA
    path("2fa/setup/", views.twofa_setup, name="2fa_setup"),
    path("2fa/verify/", views.twofa_verify, name="2fa_verify"),
    path("2fa/backup-codes/", views.twofa_backup_codes, name="2fa_backup_codes"),

    # ✅ Seguridad (pantalla dentro del sistema)
    path("seguridad/", views.security_view, name="security"),

    path("recuperar-contrasena/", views.recuperar_contrasena, name="recuperar_contrasena"),
]
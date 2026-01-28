# usuarios/services_bootstrap_admin.py
import os

from django.contrib.auth import get_user_model
from django.db import transaction

from usuarios.models import PermissionCode, Role, RolePermission


def ensure_bootstrap_admin() -> bool:
    """
    Asegura que exista un Admin inicial usando variables de entorno.
    Se puede llamar desde la vista de login (GET/POST) sin necesidad de shell.

    Retorna True si se ejecutó (enabled y con datos mínimos), False si no.
    """
    enabled = (os.getenv("BOOTSTRAP_ADMIN_ENABLED", "0") or "").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return False

    email = (os.getenv("BOOTSTRAP_ADMIN_EMAIL", "") or "").strip().lower()
    password = (os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "") or "").strip()
    first_name = (os.getenv("BOOTSTRAP_ADMIN_FIRST_NAME", "Admin") or "").strip()
    last_name = (os.getenv("BOOTSTRAP_ADMIN_LAST_NAME", "MV") or "").strip()

    if not email or not password:
        # No hay datos suficientes para crear
        return False

    reset_password = (os.getenv("BOOTSTRAP_ADMIN_RESET_PASSWORD", "0") or "").strip().lower() in (
        "1", "true", "yes", "on"
    )

    # Permisos base mínimos
    base_perms = [
        ("usuarios.modulo_acceder", "Acceder módulo Usuarios"),
        ("usuarios.usuarios_ver", "Ver usuarios"),
        ("usuarios.usuarios_editar", "Crear/Editar usuarios"),
        ("usuarios.roles_ver", "Ver roles"),
        ("usuarios.roles_editar", "Crear/Editar roles"),
        ("finanzas_comercial.modulo_acceder", "Acceder módulo Finanzas/Comercial"),
    ]

    User = get_user_model()

    def set_if_exists(obj, field, value) -> bool:
        if hasattr(obj, field):
            setattr(obj, field, value)
            return True
        return False

    with transaction.atomic():
        # 1) PermissionCodes
        for code, label in base_perms:
            PermissionCode.objects.get_or_create(code=code, defaults={"label": label})

        # 2) Rol Admin
        admin_role, _ = Role.objects.get_or_create(
            name="Admin",
            defaults={"require_2fa": True, "is_active": True},
        )
        changed = False
        if not admin_role.is_active:
            admin_role.is_active = True
            changed = True
        if not admin_role.require_2fa:
            admin_role.require_2fa = True
            changed = True
        if changed:
            admin_role.save(update_fields=["is_active", "require_2fa"])

        # 3) Permisos al rol
        perms = PermissionCode.objects.filter(code__in=[c for c, _ in base_perms])
        for p in perms:
            RolePermission.objects.get_or_create(role=admin_role, permission=p)

        # 4) Usuario
        u = User.objects.filter(email=email).first() or User.objects.filter(username=email).first()

        if not u:
            u = User(
                username=email,
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
                is_staff=True,
                is_superuser=True,
            )
            u.set_password(password)

            # Desbloqueo si tu modelo lo usa
            set_if_exists(u, "failed_login_attempts", 0)
            set_if_exists(u, "is_locked", False)
            set_if_exists(u, "locked_until", None)
            set_if_exists(u, "blocked_until", None)
            set_if_exists(u, "is_blocked", False)

            u.save()
        else:
            # Flags base
            u_changed_fields = []

            if getattr(u, "first_name", "") != first_name:
                u.first_name = first_name
                u_changed_fields.append("first_name")

            if getattr(u, "last_name", "") != last_name:
                u.last_name = last_name
                u_changed_fields.append("last_name")

            if not getattr(u, "is_active", False):
                u.is_active = True
                u_changed_fields.append("is_active")

            if not getattr(u, "is_staff", False):
                u.is_staff = True
                u_changed_fields.append("is_staff")

            if not getattr(u, "is_superuser", False):
                u.is_superuser = True
                u_changed_fields.append("is_superuser")

            # Desbloqueo
            if set_if_exists(u, "failed_login_attempts", 0):
                u_changed_fields.append("failed_login_attempts")
            if set_if_exists(u, "is_locked", False):
                u_changed_fields.append("is_locked")
            if set_if_exists(u, "locked_until", None):
                u_changed_fields.append("locked_until")
            if set_if_exists(u, "blocked_until", None):
                u_changed_fields.append("blocked_until")
            if set_if_exists(u, "is_blocked", False):
                u_changed_fields.append("is_blocked")

            # Reset password opcional
            if reset_password:
                u.set_password(password)
                # guardamos completo para asegurar hash
                u.save()
            else:
                if u_changed_fields:
                    # sin password
                    u.save(update_fields=list(dict.fromkeys(u_changed_fields)))

        # 5) Asignar rol Admin
        try:
            u.roles.add(admin_role)
        except Exception:
            pass

    return True
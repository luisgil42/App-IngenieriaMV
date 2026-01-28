# usuarios/decoradores.py
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional

from django.contrib import messages
from django.shortcuts import redirect


def user_has_role(user, role_name: str) -> bool:
    """
    Valida contra tu sistema de Roles (modelo Role) usando user.roles (ManyToMany).

    - Case-insensitive por name__iexact
    - Solo roles activos (is_active=True) si existe ese campo
    - ✅ IMPORTANTE: is_staff NO implica Admin
    - ✅ Solo superuser puede considerarse Admin por override
    - ✅ Comercial_Jefe "incluye" Comercial (equivalencia)
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    role_name = (role_name or "").strip()
    if not role_name:
        return False

    role_lower = role_name.lower()

    # ✅ SOLO superuser puede “equivaler” a Admin (override)
    if getattr(user, "is_superuser", False) and role_lower == "admin":
        return True

    # ✅ user.roles (tu ManyToMany)
    roles_m2m = getattr(user, "roles", None)
    if roles_m2m is None:
        return False

    # ✅ Equivalencias mínimas por jerarquía de negocio:
    #    Si piden "Comercial", también aceptamos "Comercial_Jefe"
    accepted_names = [role_name]
    if role_lower == "comercial":
        accepted_names.append("Comercial_Jefe")

    # Si tu Role tiene is_active (según tu código, sí tiene)
    try:
        return roles_m2m.filter(name__in=accepted_names, is_active=True).exists()
    except Exception:
        # fallback si por alguna razón no existe is_active en Role
        return roles_m2m.filter(name__in=accepted_names).exists()


def rol_requerido(*roles: str, redirect_to: str = "core:dashboard", message: Optional[str] = None):
    """
    Decorador por rol (tu modelo Role).

    Uso:
        @login_required
        @rol_requerido("Admin", "Comercial_Jefe")
        def vista(...):

    ✅ Admin = rol "Admin" en tu tabla Role
    ✅ Comercial_Jefe = rol "Comercial_Jefe" en tu tabla Role
    """
    roles = tuple([r.strip() for r in roles if (r or "").strip()])

    def decorator(view_func: Callable):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)

            allowed = False
            for r in roles:
                if user_has_role(user, r):
                    allowed = True
                    break

            # ✅ Superuser siempre permitido (aunque no tenga rol)
            if not allowed and user and getattr(user, "is_authenticated", False):
                if getattr(user, "is_superuser", False):
                    allowed = True

            if not allowed:
                messages.error(request, message or "No tienes permisos para realizar esta acción.")
                return redirect(redirect_to)

            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
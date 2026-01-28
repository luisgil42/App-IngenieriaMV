# finanzas_comercial/permissions_ui.py
from django.contrib import messages

from usuarios.decoradores import user_has_role


def can_access_finanzas(user) -> bool:
    """
    Acceso al módulo:
    - Superuser
    - O rol Comercial / Comercial_Jefe
    - O permiso finanzas_comercial.modulo_acceder (tu sistema has_perm_code)
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    # ✅ Jerarquía por rol: Comercial_Jefe "incluye" Comercial
    if user_has_role(user, "Comercial") or user_has_role(user, "Comercial_Jefe"):
        return True

    # ✅ Permiso por código (tu RBAC)
    if hasattr(user, "has_perm_code") and user.has_perm_code("finanzas_comercial.modulo_acceder"):
        return True

    return False


def ensure_finanzas_access(request) -> bool:
    if not can_access_finanzas(request.user):
        messages.error(request, "No tienes permisos para acceder a Finanzas Comercial.")
        return False
    return True


def can_delete_finanzas(user) -> bool:
    """
    Eliminar (Contactos/Empresas/Negocios):
    - Superuser
    - Comercial_Jefe
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    return user_has_role(user, "Comercial_Jefe")


# ✅ COMPAT: algunos módulos antiguos importan can_delete_comercial
def can_delete_comercial(user) -> bool:
    return can_delete_finanzas(user)
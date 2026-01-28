from common.permissions import user_has_perm_code


def menu_context(request):
    user = request.user
    can_finanzas = user_has_perm_code(user, "finanzas_comercial.modulo_acceder")
    can_usuarios = user_has_perm_code(user, "usuarios.modulo_acceder")

    return {
        "MENU": {
            "finanzas_comercial": can_finanzas,
            "usuarios": can_usuarios,
        }
    }
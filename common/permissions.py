#permissions.py

from functools import wraps

from django.http import HttpResponseForbidden


def user_has_perm_code(user, code: str) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm_code(code)

from django.contrib import messages
from django.shortcuts import render


def require_perm(code: str):
    def _decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.has_perm_code(code):
                return view_func(request, *args, **kwargs)

            # si quieres, mensaje flash
            messages.error(request, "No tienes permisos para acceder a esta sección.")
            return render(request, "common/no_permission.html", status=403)

        return _wrapped
    return _decorator
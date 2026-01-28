# common/middleware.py
from datetime import timedelta

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from usuarios.services_trusted import get_valid_trusted_device_from_cookie


class Require2FAMiddleware:
    """
    Reglas:
    - DEV (DEBUG=True): exige 2FA SOLO desde TWO_FACTOR_ENFORCE_DATE (fecha global)
    - PROD (DEBUG=False): exige 2FA por user.requires_2fa O por fecha global

    Flujo cuando exige 2FA:
      - Si NO tiene 2FA confirmado -> /usuarios/2fa/setup/
      - Si tiene 2FA confirmado:
          - Si session otp_verified_at está vigente -> OK
          - Si hay cookie trusted device válida -> OK + refresca otp_verified_at
          - Si no -> /usuarios/2fa/verify/
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        # No autenticado
        if not user or not user.is_authenticated:
            return self.get_response(request)

        # ✅ Enforce global por fecha (si está seteada)
        enforce_date = getattr(settings, "TWO_FACTOR_ENFORCE_DATE", None)
        today = timezone.localdate()
        enforce_global = bool(enforce_date and today >= enforce_date)

        # ✅ DEV: solo por fecha global (mañana, etc.)
        # ✅ PROD: por user.requires_2fa O por fecha global
        if getattr(settings, "DEBUG", False):
            requires_2fa = enforce_global
        else:
            requires_2fa = bool(getattr(user, "requires_2fa", False) or enforce_global)

        # No requiere 2FA
        if not requires_2fa:
            return self.get_response(request)

        path = request.path or ""

        # ---- Exentos (IMPORTANTE para no hacer loop) ----
        exempt = []
        for name in (
            "usuarios:login",
            "usuarios:logout",
            "usuarios:2fa_setup",
            "usuarios:2fa_verify",
            "usuarios:2fa_backup_codes",
        ):
            try:
                exempt.append(reverse(name))
            except Exception:
                pass

        static_url = getattr(settings, "STATIC_URL", "/static/") or "/static/"
        media_url = getattr(settings, "MEDIA_URL", "/media/") or "/media/"

        if (
            any(path.startswith(p) for p in exempt)
            or path.startswith(static_url)
            or path.startswith(media_url)
        ):
            return self.get_response(request)

        # ---- 1) Si no tiene 2FA confirmado: SIEMPRE setup ----
        if not user.has_confirmed_2fa():
            return redirect("usuarios:2fa_setup")

        # ---- 2) Si ya verificó recientemente en sesión: OK ----
        verified_at_str = request.session.get("otp_verified_at")
        verified_at = None
        if verified_at_str:
            try:
                verified_at = timezone.datetime.fromisoformat(verified_at_str)
                if timezone.is_naive(verified_at):
                    verified_at = timezone.make_aware(verified_at, timezone.get_current_timezone())
            except Exception:
                verified_at = None

        max_age = timedelta(days=int(getattr(settings, "TRUSTED_DEVICE_DAYS", 90)))

        if verified_at and (timezone.now() - verified_at) <= max_age:
            request.session["otp_verified"] = True
            return self.get_response(request)

        # ---- 3) Si hay dispositivo confiable por cookie: OK ----
        cookie_name = getattr(settings, "TRUSTED_DEVICE_COOKIE_NAME", "mv_td")
        dev = get_valid_trusted_device_from_cookie(request, cookie_name=cookie_name)

        if dev and dev.user_id == user.id:
            request.session["otp_verified"] = True
            request.session["otp_verified_at"] = timezone.now().isoformat()
            return self.get_response(request)

        # ---- 4) Si no hay nada válido: verify ----
        request.session["otp_verified"] = False
        request.session.pop("otp_verified_at", None)
        return redirect("usuarios:2fa_verify")


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "same-origin"
        return response
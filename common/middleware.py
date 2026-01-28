# common/middleware.py
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from usuarios.services_trusted import get_valid_trusted_device_from_cookie


class IdleLogoutMiddleware:
    """
    Cierra sesión por inactividad (idle timeout).

    - Usa SESSION_COOKIE_AGE como timeout (por defecto 3600 = 1 hora).
    - Considera actividad: cualquier request autenticada.
    - Excluye login/logout/2fa/static/media para evitar loops.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout_seconds = int(getattr(settings, "SESSION_COOKIE_AGE", 3600))

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = request.path or ""

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

        if not user or not user.is_authenticated:
            return self.get_response(request)

        now = timezone.now()

        last_str = request.session.get("last_activity")
        last_dt = None
        if last_str:
            try:
                last_dt = timezone.datetime.fromisoformat(last_str)
                if timezone.is_naive(last_dt):
                    last_dt = timezone.make_aware(last_dt, timezone.get_current_timezone())
            except Exception:
                last_dt = None

        if last_dt:
            idle = (now - last_dt).total_seconds()
            if idle >= self.timeout_seconds:
                logout(request)
                request.session.flush()
                messages.warning(request, "Tu sesión expiró por inactividad. Inicia sesión nuevamente.")
                return redirect("usuarios:login")

        request.session["last_activity"] = now.isoformat()
        return self.get_response(request)


class Require2FAMiddleware:
    """
    Reglas:
    - DEV (DEBUG=True): exige 2FA SOLO desde TWO_FACTOR_ENFORCE_DATE (fecha global)
    - PROD (DEBUG=False): exige 2FA por user.requires_2fa O por fecha global

    Flujo cuando exige 2FA:
      - Si NO tiene 2FA confirmado -> /usuarios/2fa/setup/
      - Si tiene 2FA confirmado:
          - Si session otp_verified_at está vigente (1 hora) -> OK
          - (opcional) Si hay cookie trusted device válida -> OK
          - Si no -> /usuarios/2fa/verify/
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated:
            return self.get_response(request)

        enforce_date = getattr(settings, "TWO_FACTOR_ENFORCE_DATE", None)
        today = timezone.localdate()
        enforce_global = bool(enforce_date and today >= enforce_date)

        # DEV: solo por fecha global
        # PROD: por requires_2fa del user o por fecha global
        if getattr(settings, "DEBUG", False):
            requires_2fa = enforce_global
        else:
            requires_2fa = bool(getattr(user, "requires_2fa", False) or enforce_global)

        if not requires_2fa:
            return self.get_response(request)

        path = request.path or ""

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

        # 1) Si no tiene 2FA confirmado: setup
        if not user.has_confirmed_2fa():
            return redirect("usuarios:2fa_setup")

        # 2) Validación por sesión (1 hora)
        verified_at_str = request.session.get("otp_verified_at")
        verified_at = None
        if verified_at_str:
            try:
                verified_at = timezone.datetime.fromisoformat(verified_at_str)
                if timezone.is_naive(verified_at):
                    verified_at = timezone.make_aware(verified_at, timezone.get_current_timezone())
            except Exception:
                verified_at = None

        otp_seconds = int(getattr(settings, "OTP_VERIFIED_AGE_SECONDS", getattr(settings, "SESSION_COOKIE_AGE", 3600)))
        otp_max_age = timedelta(seconds=otp_seconds)

        if verified_at and (timezone.now() - verified_at) <= otp_max_age:
            request.session["otp_verified"] = True
            return self.get_response(request)

        # 3) Trusted device (cookie) -> en PROD lo permitimos
        # Si quieres que también funcione en DEV, borra este "if not DEBUG"
        if not getattr(settings, "DEBUG", False):
            cookie_name = getattr(settings, "TRUSTED_DEVICE_COOKIE_NAME", "mv_td")
            dev = get_valid_trusted_device_from_cookie(request, cookie_name=cookie_name)
            if dev and dev.user_id == user.id:
                request.session["otp_verified"] = True
                request.session["otp_verified_at"] = timezone.now().isoformat()
                return self.get_response(request)

        # 4) Si nada válido: verify
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
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import TrustedDevice


def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "").strip()


def make_trusted_device(user, request, days: int = 90):
    """
    Crea un TrustedDevice y retorna (raw_token, trusted_device).
    - raw_token va en cookie (plano)
    - DB guarda solo hash (token_hash)
    """
    raw = secrets.token_urlsafe(48)
    token_hash = TrustedDevice.hash_token(raw)

    ip = _get_client_ip(request)
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:1000]

    now = timezone.now()

    td = TrustedDevice.objects.create(
        user=user,
        token_hash=token_hash,
        ip_address=ip,
        user_agent=ua,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=days),
        revoked_at=None,
    )
    return raw, td


def verify_trusted_device(user, raw_token: str):
    """
    Valida raw_token (cookie) y retorna TrustedDevice o None.
    """
    if not raw_token:
        return None

    token_hash = TrustedDevice.hash_token(raw_token)

    td = (
        TrustedDevice.objects.filter(
            user=user,
            token_hash=token_hash,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )
    if not td:
        return None

    td.mark_used()
    return td


def get_valid_trusted_device_from_cookie(request, user=None):
    """
    ✅ Esta es la función que tu middleware está importando.
    Lee la cookie y valida el dispositivo.

    Retorna TrustedDevice o None.
    """
    if user is None:
        user = getattr(request, "user", None)

    if not user or not getattr(user, "is_authenticated", False):
        return None

    cookie_name = getattr(settings, "TRUSTED_DEVICE_COOKIE_NAME", "mv_td")
    raw = request.COOKIES.get(cookie_name)
    return verify_trusted_device(user, raw)


def revoke_trusted_device(user, device_id: int):
    TrustedDevice.objects.filter(
        user=user,
        id=device_id,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())


def revoke_all_trusted_devices(user):
    TrustedDevice.objects.filter(
        user=user,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())
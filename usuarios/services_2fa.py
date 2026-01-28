# usuarios/services_2fa.py
import base64
from io import BytesIO
from typing import List, Tuple

import qrcode
from django.utils import timezone
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice


def get_or_create_totp_device(user) -> TOTPDevice:
    """
    Retorna un TOTPDevice (no confirmado si recién se crea).
    Mantiene 1 device principal por usuario (name='default').
    """
    device, _ = TOTPDevice.objects.get_or_create(
        user=user,
        name="default",
        defaults={"confirmed": False},
    )
    return device


def confirm_totp_device(device: TOTPDevice, token: str) -> bool:
    """
    Confirma el TOTP: verifica el token, deja el device confirmado
    y marca user.twofa_confirmed=True (tu flag propio).
    """
    token = (token or "").strip().replace(" ", "")
    if not token.isdigit():
        return False

    ok = device.verify_token(int(token))
    if not ok:
        return False

    if not device.confirmed:
        device.confirmed = True
        device.save(update_fields=["confirmed"])

    # ✅ CLAVE: marcar al usuario como 2FA confirmado
    user = device.user
    if hasattr(user, "twofa_confirmed") and not user.twofa_confirmed:
        user.twofa_confirmed = True
        user.save(update_fields=["twofa_confirmed"])

    return True


def make_qr_data_uri(otpauth_url: str) -> str:
    """
    Devuelve data:image/png;base64,... para embeber en <img src="...">
    """
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(otpauth_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")

    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def generate_backup_codes(user, count: int = 10) -> List[str]:
    """
    Genera códigos de respaldo (solo una vez) usando django_otp StaticDevice.
    """
    sdev, _ = StaticDevice.objects.get_or_create(user=user, name="backup")
    # limpiar tokens viejos para regenerar una tanda
    StaticToken.objects.filter(device=sdev).delete()

    codes = []
    for _ in range(count):
        tok = StaticToken.random_token()
        StaticToken.objects.create(device=sdev, token=tok)
        codes.append(tok)
    return codes


def verify_any_otp(user, token: str) -> Tuple[bool, str]:
    """
    Verifica token TOTP o backup codes. Retorna (ok, kind).
    """
    token = (token or "").strip().replace(" ", "")
    if not token.isdigit():
        # backup codes también pueden ser numéricos, pero aquí asumimos num
        pass

    # 1) TOTP confirmado
    tdev = (
        TOTPDevice.objects
        .filter(user=user, confirmed=True)
        .order_by("-id")
        .first()
    )
    if tdev and token.isdigit() and tdev.verify_token(int(token)):
        return True, "totp"

    # 2) Backup codes
    sdev = StaticDevice.objects.filter(user=user, name="backup").first()
    if sdev:
        # check_token consume el token si es válido
        ok = sdev.verify_token(token)
        if ok:
            return True, "backup"

    return False, "invalid"
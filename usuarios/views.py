from functools import wraps

from django.conf import settings
# usuarios/views.py
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
# django-otp (para saber si tiene 2FA confirmado y para resetear)
from django_otp.plugins.otp_totp.models import TOTPDevice

from .forms import (LoginForm, OTPVerifyForm, RoleForm, TOTPSetupVerifyForm,
                    UserForm)
from .models import PermissionCode, Role, RolePermission, TrustedDevice, User
from .services_2fa import (confirm_totp_device, generate_backup_codes,
                           get_or_create_totp_device, make_qr_data_uri,
                           verify_any_otp)
from .services_trusted import (make_trusted_device, revoke_all_trusted_devices,
                               revoke_trusted_device, verify_trusted_device)


def require_perm(code: str):
    """
    Decorador: exige permiso 'code'.
    - Superuser pasa.
    - Si tu User tiene has_perm_code (tu sistema), lo usa.
    - Si no, intenta con user.has_perm (Django).
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)

            if not user or not user.is_authenticated:
                return redirect("usuarios:login")

            if getattr(user, "is_superuser", False):
                return view_func(request, *args, **kwargs)

            # 1) Permisos por tu sistema (User.has_perm_code)
            try:
                if hasattr(user, "has_perm_code") and user.has_perm_code(code):
                    return view_func(request, *args, **kwargs)
            except Exception:
                pass

            # 2) Permisos Django nativos
            try:
                if user.has_perm(code):
                    return view_func(request, *args, **kwargs)
            except Exception:
                pass

            messages.error(request, "No tienes permisos para acceder a esta sección.")
            return redirect("core:dashboard")
        return _wrapped
    return decorator

# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------
def _post_bool(request, name: str, default: bool = False) -> bool:
    if request.method != "POST":
        return default
    return request.POST.get(name) in ("1", "on", "true", "yes")


def _post_str(request, name: str, default: str = "") -> str:
    if request.method != "POST":
        return default
    return (request.POST.get(name) or "").strip()


def _post_role_ids(request):
    vals = []
    for x in request.POST.getlist("role_ids"):
        try:
            vals.append(int(x))
        except Exception:
            pass
    return vals


def _validate_passwords(p1: str, p2: str, required: bool):
    errors = []
    if required and (not p1 or not p2):
        errors.append("La contraseña es obligatoria.")
        return errors

    # si no requerida y ambas vacías => OK
    if not p1 and not p2:
        return errors

    if p1 != p2:
        errors.append("Las contraseñas no coinciden.")

    if p1 and len(p1) < 6:
        errors.append("La contraseña debe tener al menos 6 caracteres.")

    return errors


def _admin_role_id():
    r = Role.objects.filter(name__iexact="Admin", is_active=True).first()
    return r.id if r else None


def _admin_selected(role_ids):
    aid = _admin_role_id()
    return bool(aid and aid in role_ids)

# -----------------------------------------------------------------------------
# Bootstrap de permisos + Roles base (Admin / Comercial)
# -----------------------------------------------------------------------------
def _ensure_base_permissions():
    base = [
        ("usuarios.modulo_acceder", "Acceder módulo Usuarios"),
        ("usuarios.usuarios_ver", "Ver usuarios"),
        ("usuarios.usuarios_editar", "Crear/Editar usuarios"),
        ("usuarios.roles_ver", "Ver roles"),
        ("usuarios.roles_editar", "Crear/Editar roles"),
        ("finanzas_comercial.modulo_acceder", "Acceder módulo Finanzas/Comercial"),
    ]
    for code, label in base:
        PermissionCode.objects.get_or_create(code=code, defaults={"label": label})

def _ensure_base_roles():
    """
    Crea los roles mínimos:
    - Admin (requiere 2FA)
    - Comercial (por defecto NO requiere 2FA al crearse, pero luego se puede editar)

    ✅ Si ya existen:
      - Admin: se fuerza require_2fa=True siempre (y activo)
      - Comercial: solo se reactiva si estaba inactivo (NO se pisa require_2fa)
    """
    admin_role, _ = Role.objects.get_or_create(
        name="Admin",
        defaults={"require_2fa": True, "is_active": True},
    )

    # Admin SIEMPRE activo y SIEMPRE con 2FA
    changed = False
    if not admin_role.is_active:
        admin_role.is_active = True
        changed = True
    if not admin_role.require_2fa:
        admin_role.require_2fa = True
        changed = True
    if changed:
        admin_role.save(update_fields=["is_active", "require_2fa"])

    comercial_role, created = Role.objects.get_or_create(
        name="Comercial",
        defaults={"require_2fa": False, "is_active": True},
    )

    # Comercial: solo reactivar si estaba inactivo
    if not comercial_role.is_active:
        comercial_role.is_active = True
        comercial_role.save(update_fields=["is_active"])

    # ✅ IMPORTANTE:
    # NO forzamos comercial_role.require_2fa a False aquí.
    # Si el usuario lo cambió desde la UI, se respeta.

    return admin_role, comercial_role

def _assign_permissions_to_role(role: Role, perm_codes):
    perms = PermissionCode.objects.filter(code__in=list(perm_codes))
    for perm in perms:
        RolePermission.objects.get_or_create(role=role, permission=perm)


def _ensure_roles_and_permissions():
    """
    1) Crea PermissionCode base
    2) Crea/asegura roles Admin/Comercial (activos)
    3) Asigna permisos por rol
    4) Agrega Admin a superusers
    """
    _ensure_base_permissions()
    admin_role, comercial_role = _ensure_base_roles()

    # ✅ Admin: todo lo base
    _assign_permissions_to_role(admin_role, [
        "usuarios.modulo_acceder",
        "usuarios.usuarios_ver",
        "usuarios.usuarios_editar",
        "usuarios.roles_ver",
        "usuarios.roles_editar",
        "finanzas_comercial.modulo_acceder",
    ])

    # ✅ Comercial: solo acceso al módulo comercial
    _assign_permissions_to_role(comercial_role, [
        "finanzas_comercial.modulo_acceder",
    ])

    # ✅ Superusers siempre con rol Admin
    for su in User.objects.filter(is_superuser=True):
        su.roles.add(admin_role)

def _get_pre_2fa_user(request):
    uid = request.session.get("pre_2fa_user_id")
    if not uid:
        return None
    return User.objects.filter(id=uid).first()


def _trusted_cookie_name() -> str:
    return getattr(settings, "TRUSTED_DEVICE_COOKIE_NAME", "mv_td")


# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    # guarda next (para volver donde el usuario quería entrar)
    next_url = (request.GET.get("next") or "").strip()
    if next_url:
        request.session["post_login_next"] = next_url

    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.user

        # ✅ Misma lógica que el middleware:
        # DEV: solo por fecha global
        # PROD: por user.requires_2fa O por fecha global
        enforce_date = getattr(settings, "TWO_FACTOR_ENFORCE_DATE", None)
        today = timezone.localdate()
        enforce_global = bool(enforce_date and today >= enforce_date)

        if getattr(settings, "DEBUG", False):
            requires_2fa = enforce_global
        else:
            requires_2fa = bool(getattr(user, "requires_2fa", False) or enforce_global)

        # Si requiere 2FA:
        if requires_2fa:
            # Si ya tiene 2FA confirmado, intentamos saltar con dispositivo confiable
            if user.has_confirmed_2fa():
                raw = request.COOKIES.get(_trusted_cookie_name(), "") or ""
                td = verify_trusted_device(user, raw)

                if td:
                    # ✅ marcar uso del dispositivo
                    try:
                        td.mark_used()
                    except Exception:
                        pass

                    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                    request.session["otp_verified"] = True
                    request.session["otp_verified_at"] = timezone.now().isoformat()
                    messages.success(request, "Acceso permitido (dispositivo de confianza).")
                    return redirect(request.session.pop("post_login_next", None) or "core:dashboard")

                # ✅ token presente pero inválido/expirado -> borrar cookie para evitar loops
                if raw:
                    request.session["pre_2fa_user_id"] = user.id
                    request.session["otp_verified"] = False
                    request.session.pop("otp_verified_at", None)

                    messages.info(request, "Verifica 2FA para continuar.")
                    resp = redirect("usuarios:2fa_verify")

                    resp.delete_cookie(
                        _trusted_cookie_name(),
                        samesite=getattr(settings, "TRUSTED_DEVICE_COOKIE_SAMESITE", "Lax"),
                    )
                    return resp

            # flujo normal: pre-2fa
            request.session["pre_2fa_user_id"] = user.id
            request.session["otp_verified"] = False
            request.session.pop("otp_verified_at", None)

            messages.info(request, "Verifica 2FA para continuar.")
            if user.has_confirmed_2fa():
                return redirect("usuarios:2fa_verify")
            return redirect("usuarios:2fa_setup")

        # Si no requiere 2FA
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session["otp_verified"] = True
        request.session["otp_verified_at"] = timezone.now().isoformat()
        return redirect(request.session.pop("post_login_next", None) or "core:dashboard")

    return render(request, "usuarios/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.success(request, "Sesión cerrada.")
    return redirect("usuarios:login")


# -----------------------------------------------------------------------------
# 2FA
# -----------------------------------------------------------------------------
def twofa_setup(request):
    """
    Setup inicial (QR + confirmar código).
    Si venías forzado por middleware, llega con ?forced=1
    """
    forced = (request.GET.get("forced") or "").strip() in ("1", "true", "yes", "on")

    user = request.user if request.user.is_authenticated else _get_pre_2fa_user(request)
    if not user:
        return redirect("usuarios:login")

    device = get_or_create_totp_device(user)
    otpauth = device.config_url
    qr_data_uri = make_qr_data_uri(otpauth)

    form = TOTPSetupVerifyForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        token = (form.cleaned_data["token"] or "").strip().replace(" ", "")
        if confirm_totp_device(device, token):
            # ✅ doble seguro: marcar flag propio del usuario
            if hasattr(user, "twofa_confirmed") and not user.twofa_confirmed:
                user.twofa_confirmed = True
                user.save(update_fields=["twofa_confirmed"])

            # ✅ si no estaba autenticado, ahora sí lo autenticamos
            if not request.user.is_authenticated:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")

            request.session["otp_verified"] = True
            request.session["otp_verified_at"] = timezone.now().isoformat()
            request.session.pop("pre_2fa_user_id", None)

            messages.success(request, "2FA activado correctamente.")
            codes = generate_backup_codes(user, count=10)
            request.session["backup_codes_once"] = codes

            return redirect("usuarios:2fa_backup_codes")

        messages.error(request, "Código incorrecto. Intenta nuevamente.")

    return render(
        request,
        "usuarios/2fa_setup.html",
        {
            "qr_data_uri": qr_data_uri,
            "secret": device.key,
            "form": form,
            "user": user,
            "forced": forced,
        },
    )



def twofa_backup_codes(request):
    """
    Muestra códigos SOLO una vez.
    Si un middleware te redirige en loop, es porque no estaba marcado otp_verified.
    Con el fix de arriba ya queda.
    """
    codes = request.session.pop("backup_codes_once", None)
    if not codes:
        messages.info(request, "No hay códigos nuevos para mostrar.")
        return redirect("core:dashboard")

    return render(request, "usuarios/2fa_backup_codes.html", {"codes": codes})


def twofa_verify(request):
    user = request.user if request.user.is_authenticated else _get_pre_2fa_user(request)
    if not user:
        return redirect("usuarios:login")

    # ✅ Misma lógica que middleware/login
    enforce_date = getattr(settings, "TWO_FACTOR_ENFORCE_DATE", None)
    today = timezone.localdate()
    enforce_global = bool(enforce_date and today >= enforce_date)

    if getattr(settings, "DEBUG", False):
        requires_2fa = enforce_global
    else:
        requires_2fa = bool(getattr(user, "requires_2fa", False) or enforce_global)

    # si requiere 2FA pero todavía no lo confirmó, debe ir a setup
    if requires_2fa and not user.has_confirmed_2fa():
        return redirect("usuarios:2fa_setup")

    form = OTPVerifyForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        token = (form.cleaned_data["token"] or "").strip().replace(" ", "")
        ok, kind = verify_any_otp(user, token)

        if ok:
            if not request.user.is_authenticated:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")

            request.session["otp_verified"] = True
            request.session["otp_verified_at"] = timezone.now().isoformat()
            request.session.pop("pre_2fa_user_id", None)

            remember = bool(request.POST.get("remember_device"))
            next_url = request.session.pop("post_login_next", None) or "core:dashboard"
            response = redirect(next_url)

            if remember:
                from datetime import timedelta

                days = int(getattr(settings, "TRUSTED_DEVICE_DAYS", 90))
                raw_token, _ = make_trusted_device(user, request, days=days)

                cookie_name = _trusted_cookie_name()
                secure_flag = getattr(settings, "TRUSTED_DEVICE_COOKIE_SECURE", False)
                samesite_val = getattr(settings, "TRUSTED_DEVICE_COOKIE_SAMESITE", "Lax")

                use_expires = bool(getattr(settings, "TRUSTED_DEVICE_COOKIE_USE_EXPIRES", False))
                if use_expires:
                    expires_dt = timezone.now() + timedelta(days=days)
                    response.set_cookie(
                        cookie_name,
                        raw_token,
                        expires=expires_dt,
                        httponly=True,
                        secure=secure_flag,
                        samesite=samesite_val,
                    )
                else:
                    response.set_cookie(
                        cookie_name,
                        raw_token,
                        max_age=days * 24 * 60 * 60,
                        httponly=True,
                        secure=secure_flag,
                        samesite=samesite_val,
                    )

            messages.success(request, f"2FA verificado ({kind}).")
            return response

        messages.error(request, "Código inválido.")

    return render(request, "usuarios/2fa_verify.html", {"form": form, "user": user})

# -----------------------------------------------------------------------------
# ✅ Seguridad (activar 2FA + listar/eliminar dispositivos de confianza)
# -----------------------------------------------------------------------------
@login_required
def security_view(request):
    user = request.user
    now = timezone.now()

    two_factor_enabled = user.has_confirmed_2fa()

    device = get_or_create_totp_device(user)
    otp_uri = device.config_url
    secret = device.key

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "enable_2fa":
            code = (request.POST.get("code") or "").strip().replace(" ", "")
            if not code:
                messages.error(request, "Debes ingresar un código.")
                return redirect("usuarios:security")

            if confirm_totp_device(device, code):
                messages.success(request, "✅ 2FA activado correctamente.")
            else:
                messages.error(request, "Código incorrecto. Intenta nuevamente.")
            return redirect("usuarios:security")

        if action == "delete_device":
            device_id = request.POST.get("device_id")
            if device_id:
                try:
                    revoke_trusted_device(user, int(device_id))
                    messages.success(request, "✅ Dispositivo eliminado.")
                except Exception:
                    messages.error(request, "No se pudo eliminar el dispositivo.")
            return redirect("usuarios:security")

    devices = (
        TrustedDevice.objects
        .filter(user=user, revoked_at__isnull=True, expires_at__gt=now)
        .order_by("-last_used_at", "-created_at")
    )

    devices_all = (
        TrustedDevice.objects
        .filter(user=user)
        .order_by("-last_used_at", "-created_at")
    )

    return render(request, "usuarios/security.html", {
        "two_factor_enabled": two_factor_enabled,
        "otp_uri": otp_uri,
        "secret": secret,
        "devices": devices,
        "devices_all": devices_all,
        "trusted_days": int(getattr(settings, "TRUSTED_DEVICE_DAYS", 90)),
    })


# -----------------------------------------------------------------------------
# Usuarios CRUD + ✅ Reset 2FA desde lista
# -----------------------------------------------------------------------------
@login_required
@require_perm("usuarios.usuarios_ver")
def user_list(request):
    _ensure_roles_and_permissions()
    # -------------------------
    # Acciones POST (delete / reset 2FA)
    # -------------------------
    if request.method == "POST":
        if not request.user.has_perm_code("usuarios.usuarios_editar") and not request.user.is_superuser:
            messages.error(request, "No tienes permisos para editar usuarios.")
            return redirect("usuarios:user_list")

        user_id = request.POST.get("user_id")

        if request.POST.get("delete_user"):
            u = get_object_or_404(User, pk=user_id)
            if u.pk == request.user.pk:
                messages.error(request, "No puedes eliminar tu propio usuario.")
                return redirect("usuarios:user_list")

            u.delete()
            messages.success(request, "Usuario eliminado.")
            return redirect("usuarios:user_list")

        if request.POST.get("reset_2fa"):
            u = get_object_or_404(User, pk=user_id)

            # 1) Borrar dispositivos TOTP (django-otp)
            TOTPDevice.objects.filter(user=u).delete()

            # 2) Revocar dispositivos de confianza (tu modelo)
            TrustedDevice.objects.filter(user=u).update(revoked_at=timezone.now())

            # 3) ✅ IMPORTANTE: resetear el flag propio del usuario (MV)
            if hasattr(u, "twofa_confirmed"):
                u.twofa_confirmed = False
                u.save(update_fields=["twofa_confirmed"])

            messages.success(request, "2FA reseteado. El usuario deberá configurarlo nuevamente.")
            return redirect("usuarios:user_list")

    # -------------------------
    # Filtros GET
    # -------------------------
    identidad = (request.GET.get("identidad") or "").strip()  # aquí entra RUT/Identidad
    nombre = (request.GET.get("nombre") or "").strip()
    email = (request.GET.get("email") or "").strip()
    rol = (request.GET.get("rol") or "").strip()
    activo = (request.GET.get("activo") or "").strip()

    cantidad = (request.GET.get("cantidad") or "20").strip()
    if cantidad not in {"10", "20", "50", "100"}:
        cantidad = "20"

    roles = Role.objects.filter(is_active=True).order_by("name")

    # Campos existentes en el User (para que no se rompa si aún no agregas rut)
    user_fields = {f.name for f in User._meta.get_fields() if hasattr(f, "name")}
    rut_field = "rut" if "rut" in user_fields else ("identidad" if "identidad" in user_fields else None)

    # -------------------------
    # Query principal
    # -------------------------
    qs = (
        User.objects.all()
        .prefetch_related("roles")
        .annotate(
            # ✅ 2FA activo si tiene TOTP confirmado O si tu flag propio está en True
            two_factor_enabled=Exists(
                TOTPDevice.objects.filter(user_id=OuterRef("pk"), confirmed=True)
            )
        )
        .order_by("email")
    )

    # Si existe el flag propio, lo usamos para reflejar la realidad de MV
    if "twofa_confirmed" in user_fields:
        # Nota: no se puede "OR" directo en annotate con Exists sin Case;
        # lo resolvemos a nivel de template o reemplazando el valor en Python.
        pass

    # -------------------------
    # Aplicar filtros
    # -------------------------
    if identidad:
        if rut_field:
            # rut o identidad en User
            qs = qs.filter(**{f"{rut_field}__icontains": identidad})
        else:
            # fallback si no tienes rut aún
            qs = qs.filter(
                Q(email__icontains=identidad) |
                Q(username__icontains=identidad) |
                Q(full_name__icontains=identidad) |
                Q(first_name__icontains=identidad) |
                Q(last_name__icontains=identidad)
            )

    if nombre:
        qs = qs.filter(
            Q(full_name__icontains=nombre) |
            Q(first_name__icontains=nombre) |
            Q(last_name__icontains=nombre) |
            Q(username__icontains=nombre) |
            Q(email__icontains=nombre)
        )

    if email:
        qs = qs.filter(email__icontains=email)

    if rol:
        qs = qs.filter(roles__name=rol)

    if activo == "1":
        qs = qs.filter(is_active=True)
    elif activo == "0":
        qs = qs.filter(is_active=False)

    qs = qs.distinct()

    # -------------------------
    # Paginación
    # -------------------------
    paginator = Paginator(qs, int(cantidad))
    page_number = request.GET.get("page") or 1
    pagina = paginator.get_page(page_number)

    # ✅ Ajuste final 2FA: mezcla TOTP + flag propio
    # (para que el template use u.two_factor_enabled y sea real)
    if "twofa_confirmed" in user_fields:
        for u in pagina.object_list:
            u.two_factor_enabled = bool(getattr(u, "twofa_confirmed", False)) or bool(getattr(u, "two_factor_enabled", False))

    filtros = {
        "identidad": identidad,
        "nombre": nombre,
        "email": email,
        "rol": rol,
        "activo": activo,
    }

    return render(request, "usuarios/user_list.html", {
        "roles": roles,
        "pagina": pagina,
        "cantidad": cantidad,
        "filtros": filtros,
        "rut_field": rut_field,  # por si quieres mostrar columna rut en template
    })

# -----------------------------------------------------------------------------
# Create
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Create
# -----------------------------------------------------------------------------
@login_required
@require_perm("usuarios.usuarios_editar")
def user_create(request):
    # ✅ asegura roles base (Admin/Comercial) siempre existan
    _ensure_roles_and_permissions()

    roles = Role.objects.filter(is_active=True).order_by("-id", "name")
    form_errors = []
    selected_role_ids = []

    if request.method == "POST":
        rut = _post_str(request, "rut")
        email = _post_str(request, "email").lower()
        first_name = _post_str(request, "first_name")
        last_name = _post_str(request, "last_name")
        phone = _post_str(request, "phone")

        telegram_chat_id = _post_str(request, "telegram_chat_id")
        email_notificaciones_activo = _post_bool(request, "email_notificaciones_activo", True)
        telegram_activo = _post_bool(request, "telegram_activo", False)

        is_active = _post_bool(request, "is_active", True)
        is_staff = _post_bool(request, "is_staff", False)
        is_superuser = _post_bool(request, "is_superuser", False)

        selected_role_ids = _post_role_ids(request)

        p1 = _post_str(request, "password1")
        p2 = _post_str(request, "password2")
        form_errors.extend(_validate_passwords(p1, p2, required=True))

        if not rut:
            form_errors.append("El RUT es obligatorio.")
        if not email:
            form_errors.append("El correo es obligatorio.")
        if not first_name:
            form_errors.append("El nombre es obligatorio.")
        if not last_name:
            form_errors.append("El apellido es obligatorio.")
        if User.objects.filter(email=email).exists():
            form_errors.append("Ya existe un usuario con ese correo.")
        if not selected_role_ids:
            form_errors.append("Debes seleccionar al menos un rol (Admin o Comercial).")

        # ✅ Predomina Admin => forzamos staff
        if _admin_selected(selected_role_ids):
            is_staff = True

        if not form_errors:
            u = User(
                username=email,
                email=email,
                rut=rut,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                telegram_chat_id=telegram_chat_id,
                email_notificaciones_activo=email_notificaciones_activo,
                telegram_activo=telegram_activo,
                is_active=is_active,
                is_staff=is_staff,
                is_superuser=is_superuser,
            )
            u.set_password(p1)
            u.save()
            u.roles.set(Role.objects.filter(id__in=selected_role_ids))

            messages.success(request, "✅ Usuario creado correctamente.")
            return redirect("usuarios:user_list")

    values = {
        "rut": _post_str(request, "rut"),
        "email": _post_str(request, "email"),
        "first_name": _post_str(request, "first_name"),
        "last_name": _post_str(request, "last_name"),
        "phone": _post_str(request, "phone"),
        "telegram_chat_id": _post_str(request, "telegram_chat_id"),
        "email_notificaciones_activo": _post_bool(request, "email_notificaciones_activo", True),
        "telegram_activo": _post_bool(request, "telegram_activo", False),
        "is_active": _post_bool(request, "is_active", True),
        "is_staff": _post_bool(request, "is_staff", False),
        "is_superuser": _post_bool(request, "is_superuser", False),
    }

    return render(request, "usuarios/user_form.html", {
        "is_edit": False,
        "title": "Nuevo usuario",
        "roles": roles,
        "selected_role_ids": selected_role_ids,
        "values": values,
        "form_errors": form_errors,
    })


# -----------------------------------------------------------------------------
# Edit
# -----------------------------------------------------------------------------
@login_required
@require_perm("usuarios.usuarios_editar")
def user_edit(request, pk):
    # ✅ asegura roles base (Admin/Comercial) siempre existan
    _ensure_roles_and_permissions()

    u = get_object_or_404(User, pk=pk)

    roles = Role.objects.filter(is_active=True).order_by("-id", "name")
    form_errors = []
    selected_role_ids = list(u.roles.values_list("id", flat=True))

    if request.method == "POST":
        rut = _post_str(request, "rut")
        email = _post_str(request, "email").lower()
        first_name = _post_str(request, "first_name")
        last_name = _post_str(request, "last_name")
        phone = _post_str(request, "phone")

        telegram_chat_id = _post_str(request, "telegram_chat_id")
        email_notificaciones_activo = _post_bool(request, "email_notificaciones_activo", True)
        telegram_activo = _post_bool(request, "telegram_activo", False)

        is_active = _post_bool(request, "is_active", True)
        is_staff = _post_bool(request, "is_staff", False)
        is_superuser = _post_bool(request, "is_superuser", False)

        selected_role_ids = _post_role_ids(request)

        p1 = _post_str(request, "password1")
        p2 = _post_str(request, "password2")
        form_errors.extend(_validate_passwords(p1, p2, required=False))

        if not rut:
            form_errors.append("El RUT es obligatorio.")
        if not email:
            form_errors.append("El correo es obligatorio.")
        if not first_name:
            form_errors.append("El nombre es obligatorio.")
        if not last_name:
            form_errors.append("El apellido es obligatorio.")
        if User.objects.filter(email=email).exclude(pk=u.pk).exists():
            form_errors.append("Ya existe otro usuario con ese correo.")
        if not selected_role_ids:
            form_errors.append("Debes seleccionar al menos un rol.")

        # ✅ Predomina Admin => forzamos staff
        if _admin_selected(selected_role_ids):
            is_staff = True

        if not form_errors:
            u.username = email
            u.email = email
            u.rut = rut
            u.first_name = first_name
            u.last_name = last_name
            u.phone = phone
            u.telegram_chat_id = telegram_chat_id
            u.email_notificaciones_activo = email_notificaciones_activo
            u.telegram_activo = telegram_activo
            u.is_active = is_active
            u.is_staff = is_staff
            u.is_superuser = is_superuser

            if p1:
                u.set_password(p1)

            u.save()
            u.roles.set(Role.objects.filter(id__in=selected_role_ids))

            messages.success(request, "✅ Usuario actualizado.")
            return redirect("usuarios:user_list")

    values = {
        "rut": getattr(u, "rut", "") or "",
        "email": u.email or "",
        "first_name": u.first_name or "",
        "last_name": u.last_name or "",
        "phone": getattr(u, "phone", "") or "",
        "telegram_chat_id": getattr(u, "telegram_chat_id", "") or "",
        "email_notificaciones_activo": bool(getattr(u, "email_notificaciones_activo", True)),
        "telegram_activo": bool(getattr(u, "telegram_activo", False)),
        "is_active": bool(u.is_active),
        "is_staff": bool(u.is_staff),
        "is_superuser": bool(u.is_superuser),
    }

    return render(request, "usuarios/user_form.html", {
        "is_edit": True,
        "title": "Editar usuario",
        "roles": roles,
        "selected_role_ids": selected_role_ids,
        "values": values,
        "form_errors": form_errors,
        "user_obj": u,
    })



# -----------------------------------------------------------------------------
# Roles CRUD
# -----------------------------------------------------------------------------
@login_required
@require_perm("usuarios.roles_ver")
def role_list(request):
    _ensure_roles_and_permissions()
    roles = Role.objects.order_by("name")
    return render(request, "usuarios/role_list.html", {"roles": roles})


@login_required
@require_perm("usuarios.roles_editar")
def role_create(request):
    form = RoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Rol creado.")
        return redirect("usuarios:role_list")
    return render(request, "usuarios/role_form.html", {"form": form, "title": "Nuevo rol"})


@login_required
@require_perm("usuarios.roles_editar")
def role_edit(request, pk):
    role = get_object_or_404(Role, pk=pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Rol actualizado.")
        return redirect("usuarios:role_list")
    return render(request, "usuarios/role_form.html", {"form": form, "title": "Editar rol"})


def recuperar_contrasena(request):
    return render(request, "usuarios/password_recovery.html")
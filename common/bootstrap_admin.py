# usuarios/management/commands/bootstrap_admin.py
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from usuarios.models import PermissionCode, Role, RolePermission


class Command(BaseCommand):
    help = "Crea (si no existe) un usuario Admin inicial usando variables de entorno."

    def handle(self, *args, **options):
        enabled = (os.getenv("BOOTSTRAP_ADMIN_ENABLED", "0") or "").strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            self.stdout.write(self.style.WARNING("BOOTSTRAP_ADMIN_ENABLED no está activo. No se crea nada."))
            return

        email = (os.getenv("BOOTSTRAP_ADMIN_EMAIL", "") or "").strip().lower()
        password = (os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "") or "").strip()
        first_name = (os.getenv("BOOTSTRAP_ADMIN_FIRST_NAME", "Admin") or "").strip()
        last_name = (os.getenv("BOOTSTRAP_ADMIN_LAST_NAME", "MV") or "").strip()

        if not email or not password:
            self.stdout.write(self.style.ERROR(
                "Faltan BOOTSTRAP_ADMIN_EMAIL y/o BOOTSTRAP_ADMIN_PASSWORD. No se puede bootstrapear."
            ))
            return

        reset_password = (os.getenv("BOOTSTRAP_ADMIN_RESET_PASSWORD", "0") or "").strip().lower() in ("1", "true", "yes", "on")

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

        with transaction.atomic():
            # 1) asegurar PermissionCodes
            for code, label in base_perms:
                PermissionCode.objects.get_or_create(code=code, defaults={"label": label})

            # 2) asegurar rol Admin (activo y con require_2fa True)
            admin_role, created = Role.objects.get_or_create(
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

            # 3) asignar permisos al rol Admin
            perms = PermissionCode.objects.filter(code__in=[c for c, _ in base_perms])
            for p in perms:
                RolePermission.objects.get_or_create(role=admin_role, permission=p)

            # 4) crear/asegurar usuario
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
                u.save()
                self.stdout.write(self.style.SUCCESS(f"✅ Admin creado: {email}"))
            else:
                # Asegurar flags
                upd = []
                if not u.is_staff:
                    u.is_staff = True
                    upd.append("is_staff")
                if not u.is_superuser:
                    u.is_superuser = True
                    upd.append("is_superuser")
                if not u.is_active:
                    u.is_active = True
                    upd.append("is_active")

                if reset_password:
                    u.set_password(password)
                    upd.append("password")

                if upd:
                    u.save(update_fields=upd)
                    self.stdout.write(self.style.SUCCESS(f"✅ Admin existente actualizado ({', '.join(upd)}): {email}"))
                else:
                    self.stdout.write(self.style.WARNING(f"ℹ️ Admin ya existe, no se cambió nada: {email}"))

            # 5) asignar rol Admin al usuario
            try:
                u.roles.add(admin_role)
            except Exception:
                pass

        self.stdout.write(self.style.SUCCESS("✅ bootstrap_admin terminado."))
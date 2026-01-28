import hashlib

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("El email es obligatorio")
        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    # email como identificador
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)

    # ✅ Identidad
    rut = models.CharField(max_length=20, blank=True, default="", db_index=True)

    # compatibilidad (no molesta)
    full_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    # ✅ Notificaciones (para que user_create no reviente)
    telegram_chat_id = models.CharField(max_length=64, blank=True, default="")
    email_notificaciones_activo = models.BooleanField(default=True)
    telegram_activo = models.BooleanField(default=False)

    # Política: requerido por rol o por bandera directa
    force_2fa = models.BooleanField(default=False)

    # ✅ Este flag indica que YA confirmó su 2FA (setup ok)
    twofa_confirmed = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def get_full_name(self):
        fn = (self.first_name or "").strip()
        ln = (self.last_name or "").strip()
        if fn or ln:
            return (f"{fn} {ln}").strip()

        base = (self.full_name or "").strip()
        if base:
            return base

        base2 = (super().get_full_name() or "").strip()
        return base2 or self.email

    @property
    def requires_2fa(self) -> bool:
        if self.force_2fa:
            return True
        return self.roles.filter(require_2fa=True, is_active=True).exists()

    def has_confirmed_2fa(self) -> bool:
        return bool(self.twofa_confirmed)

    def has_perm_code(self, code: str) -> bool:
        if self.is_superuser:
            return True
        return RolePermission.objects.filter(
            role__users=self,
            role__is_active=True,
            permission__code=code,
            permission__is_active=True,
        ).exists()


class Role(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    require_2fa = models.BooleanField(default=False)

    users = models.ManyToManyField(User, related_name="roles", blank=True)

    def __str__(self):
        return self.name


class PermissionCode(models.Model):
    code = models.CharField(max_length=180, unique=True)
    label = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(PermissionCode, on_delete=models.CASCADE)

    class Meta:
        unique_together = [("role", "permission")]

    def __str__(self):
        return f"{self.role} -> {self.permission}"


class TrustedDevice(models.Model):
    """
    Dispositivo de confianza:
    - Guardamos solo el hash del token (nunca el token plano)
    - Cookie almacena el token plano
    - Expira en N días (default 90)
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trusted_devices")

    token_hash = models.CharField(max_length=64, unique=True)  # sha256 hex
    user_agent = models.TextField(blank=True, default="")
    ip_address = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "expires_at"]),
            models.Index(fields=["token_hash"]),
        ]

    def __str__(self):
        return f"TrustedDevice(user={self.user_id}, exp={self.expires_at:%Y-%m-%d})"

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at > timezone.now()

    def mark_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
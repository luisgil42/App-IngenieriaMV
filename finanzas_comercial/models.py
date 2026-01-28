from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Company(models.Model):
    name = models.CharField("Nombre de la empresa", max_length=255)

    rut = models.CharField("RUT", max_length=30, blank=True, default="", db_index=True)
    city = models.CharField("Ciudad", max_length=120, blank=True, default="")
    country_region = models.CharField("País/Región", max_length=120, blank=True, default="")
    sector = models.CharField("Rubro / Sector", max_length=160, blank=True, default="")
    phone = models.CharField("Número de contacto", max_length=40, blank=True, default="")

    logo = models.ImageField(
        "Logo",
        upload_to="finanzas_comercial/company_logos/",
        blank=True,
        null=True,
    )

    last_activity_at = models.DateTimeField("Última actividad", blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="companies_created",
        verbose_name="Registrado por",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField("Fecha de creación", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["rut"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.name

    def touch_activity(self):
        self.last_activity_at = timezone.now()
        self.save(update_fields=["last_activity_at"])


class Contact(models.Model):
    first_name = models.CharField("Nombre", max_length=120)
    last_name = models.CharField("Apellido", max_length=120)

    email = models.EmailField("Correo", blank=True, null=True)
    phone = models.CharField("Número de teléfono", max_length=40, blank=True, null=True)

    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="contacts",
        verbose_name="Empresa",
    )

    job_title = models.CharField("Cargo", max_length=160, blank=True, null=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="contacts_owned",
        verbose_name="Propietario del contacto",
    )

    linkedin_url = models.URLField("LinkedIn", blank=True, null=True)

    # ✅ NUEVO: logo del contacto (si no existe, puedes usar el logo de la empresa como fallback en templates)
    logo = models.ImageField("Logo del contacto", upload_to="finanzas_comercial/contact_logos/", blank=True, null=True)

    last_activity_at = models.DateTimeField("Última actividad", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Contacto"
        verbose_name_plural = "Contactos"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def touch_activity(self):
        now = timezone.now()
        self.last_activity_at = now
        self.save(update_fields=["last_activity_at"])

        # ✅ empuja actividad a la empresa también (si existe)
        if self.company_id:
            Company.objects.filter(id=self.company_id).update(last_activity_at=now)


class DealStage(models.Model):
    name = models.CharField("Etapa", max_length=120, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="deal_stages_created",
        verbose_name="Creado por",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Etapa de negocio"
        verbose_name_plural = "Etapas de negocio"
        ordering = ["sort_order", "name", "id"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name


class Deal(models.Model):
    name = models.CharField("Nombre del negocio", max_length=255)

    stage = models.ForeignKey(
        DealStage,
        on_delete=models.PROTECT,
        related_name="deals",
        verbose_name="Etapa del negocio",
    )

    close_at = models.DateTimeField("Fecha de cierre", blank=True, null=True)

    company = models.ForeignKey(
        "finanzas_comercial.Company",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="deals",
        verbose_name="Empresa",
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="deals_owned",
        verbose_name="Propietario del negocio",
    )

    value = models.DecimalField("Valor del negocio", max_digits=18, decimal_places=2, default=0)

    last_activity_at = models.DateTimeField("Última actividad", blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="deals_created",
        verbose_name="Creado por",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField("Fecha de creación", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Negocio"
        verbose_name_plural = "Negocios"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["close_at"]),
        ]

    def __str__(self):
        return self.name

    def touch_activity(self):
        self.last_activity_at = timezone.now()
        self.save(update_fields=["last_activity_at"])


# ---------------------------------------------------------
# ✅ ADJUNTOS DE NEGOCIO (RFP iniciales + archivos analizados)
# ---------------------------------------------------------
def deal_attachment_upload_to(instance: "DealAttachment", filename: str) -> str:
    # Se separa por tipo:
    # - INICIAL: RFP y documentos de entrada
    # - ANALISIS: informes/archivos resultantes del análisis
    deal_id = instance.deal_id or "tmp"
    bucket = "inicial" if instance.category == DealAttachment.Category.INICIAL else "analisis"
    return f"finanzas_comercial/negocios/{deal_id}/{bucket}/{filename}"


class DealAttachment(models.Model):
    class Category(models.TextChoices):
        INICIAL = "INICIAL", "Inicial (RFP)"
        ANALISIS = "ANALISIS", "Análisis"

    deal = models.ForeignKey(
        Deal,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="Negocio",
    )

    category = models.CharField(
        "Tipo",
        max_length=20,
        choices=Category.choices,
        default=Category.INICIAL,
        db_index=True,
    )

    file = models.FileField("Archivo", upload_to=deal_attachment_upload_to)
    original_name = models.CharField("Nombre original", max_length=255, blank=True)
    content_type = models.CharField("Tipo MIME", max_length=100, blank=True)
    size_bytes = models.BigIntegerField("Tamaño (bytes)", default=0)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comercial_deal_attachments",
        verbose_name="Subido por",
    )
    uploaded_at = models.DateTimeField("Fecha subida", default=timezone.now)

    class Meta:
        verbose_name = "Adjunto de Negocio"
        verbose_name_plural = "Adjuntos de Negocio"
        ordering = ["-uploaded_at", "-id"]
        indexes = [
            models.Index(fields=["deal", "category"]),
            models.Index(fields=["uploaded_at"]),
        ]

    def __str__(self):
        return self.original_name or self.file.name



def task_attachment_upload_to(instance, filename: str) -> str:
    # Queda en Wasabi si tu DEFAULT_FILE_STORAGE apunta a S3/Wasabi
    return f"finanzas_comercial/tareas/{instance.task_id}/{filename}"


class Task(models.Model):
    class Status(models.TextChoices):
        EN_PROCESO = "EN_PROCESO", "En proceso"
        COMPLETADA = "COMPLETADA", "Completada"
        PEND_EXTERNO = "PEND_EXTERNO", "Pendiente por persona externa"

    title = models.CharField("Título", max_length=255)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comercial_tasks_assigned",
        verbose_name="Asignada a",
    )

    contact = models.ForeignKey(
        "finanzas_comercial.Contact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name="Contacto asociado",
    )

    company = models.ForeignKey(
        "finanzas_comercial.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name="Empresa asociada",
    )

    due_at = models.DateTimeField("Fecha de vencimiento", null=True, blank=True)
    description = models.TextField("Descripción", blank=True)

    notify_by_email = models.BooleanField("Notificar por correo al crear", default=False)

    status = models.CharField(
        "Estatus",
        max_length=20,
        choices=Status.choices,
        default=Status.EN_PROCESO,
        db_index=True,
    )

    status_comment = models.TextField("Comentario del estatus", blank=True)

    completed_at = models.DateTimeField("Fecha de completada", null=True, blank=True)

    is_active = models.BooleanField("Activa", default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comercial_tasks_created",
        verbose_name="Creada por",
    )

    created_at = models.DateTimeField("Fecha creación", default=timezone.now, db_index=True)
    updated_at = models.DateTimeField("Última actualización", auto_now=True)

    class Meta:
        verbose_name = "Tarea Comercial"
        verbose_name_plural = "Tareas Comerciales"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["due_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"#{self.pk} - {self.title}"

    @property
    def is_overdue(self) -> bool:
        if not self.due_at:
            return False
        if self.status != self.Status.EN_PROCESO:
            return False
        return timezone.now() > self.due_at


class TaskAttachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments", verbose_name="Tarea")

    file = models.FileField("Archivo", upload_to=task_attachment_upload_to)
    original_name = models.CharField("Nombre original", max_length=255, blank=True)
    content_type = models.CharField("Tipo MIME", max_length=100, blank=True)
    size_bytes = models.BigIntegerField("Tamaño (bytes)", default=0)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comercial_task_attachments",
        verbose_name="Subido por",
    )
    uploaded_at = models.DateTimeField("Fecha subida", default=timezone.now)

    class Meta:
        verbose_name = "Adjunto de Tarea"
        verbose_name_plural = "Adjuntos de Tarea"
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return self.original_name or self.file.name
    





def quote_pdf_upload_to(instance: "Quote", filename: str) -> str:
    # Queda en Wasabi/S3 si DEFAULT_FILE_STORAGE apunta a S3/Wasabi
    return f"finanzas_comercial/cotizaciones/{instance.id}/{filename}"


class Quote(models.Model):
    class Status(models.TextChoices):
        CREADA = "CREADA", "Creada"
        ENVIADA = "ENVIADA", "Enviada"
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"
        EN_MODIFICACION = "EN_MODIFICACION", "En modificación"

    class Currency(models.TextChoices):
        CLP = "CLP", "CLP"
        USD = "USD", "USD"

    title = models.CharField("Título del presupuesto", max_length=255)

    status = models.CharField(
        "Estado de la cotización",
        max_length=20,
        choices=Status.choices,
        default=Status.CREADA,
        db_index=True,
    )
    status_comment = models.TextField("Comentario del estado", blank=True, default="")

    # ✅ Moneda (CLP / USD)
    currency = models.CharField(
        "Moneda",
        max_length=3,
        choices=Currency.choices,
        default=Currency.CLP,
        db_index=True,
    )

    # ✅ Descuento extra (opcional, a nivel de cotización)
    extra_discount_name = models.CharField("Nombre descuento", max_length=120, blank=True, default="")
    extra_discount_pct = models.DecimalField(
        "Descuento extra (%)",
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    # Importe principal (se guarda el total final calculado)
    # (mantengo el nombre amount_clp por compatibilidad con tu app, aunque ahora representa el total en la moneda elegida)
    amount_clp = models.DecimalField("Importe del presupuesto", max_digits=18, decimal_places=2, default=0)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="commercial_quotes_owned",
        verbose_name="Propietario de la cotización",
        blank=True,
        null=True,
    )

    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="commercial_quotes_prepared",
        verbose_name="Preparado por",
        blank=True,
        null=True,
    )

    # Relación con negocio
    deal = models.ForeignKey(
        "finanzas_comercial.Deal",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="quotes",
        verbose_name="Negocio asociado",
    )

    # Contactos (permitimos 1 o 2; se valida en el form)
    contacts = models.ManyToManyField(
        "finanzas_comercial.Contact",
        related_name="quotes",
        blank=True,
        verbose_name="Contactos asociados",
    )

    created_at = models.DateTimeField("Fecha de creación", default=timezone.now, db_index=True)
    expires_at = models.DateTimeField("Fecha de vencimiento", blank=True, null=True, db_index=True)

    # Contenido general del documento
    comments = models.TextField("Comentarios", blank=True, default="")
    purchase_conditions = models.TextField("Condiciones de compra", blank=True, default="")

    # PDF generado
    pdf_file = models.FileField("Cotización PDF", upload_to=quote_pdf_upload_to, blank=True, null=True)
    pdf_reference = models.CharField("Referencia", max_length=80, blank=True, default="", db_index=True)

    is_active = models.BooleanField("Activa", default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="commercial_quotes_created",
        verbose_name="Creada por",
    )

    updated_at = models.DateTimeField("Última actualización", auto_now=True)

    class Meta:
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["pdf_reference"]),
            models.Index(fields=["currency"]),
        ]

    def __str__(self) -> str:
        return f"#{self.pk} - {self.title}"

    # -----------------------------
    # Cálculos desde líneas
    # -----------------------------
    @property
    def lines_subtotal_gross(self) -> Decimal:
        """Subtotal bruto (qty * unit_price) sin descuentos por línea."""
        s = Decimal("0")
        for ln in self.lines.all():
            q = ln.qty or Decimal("0")
            p = ln.unit_price_clp or Decimal("0")
            s += (q * p)
        return s

    @property
    def lines_discount_total(self) -> Decimal:
        """Total de descuentos aplicados en líneas (sumatoria)."""
        s = Decimal("0")
        for ln in self.lines.all():
            q = ln.qty or Decimal("0")
            p = ln.unit_price_clp or Decimal("0")
            gross = q * p

            d = ln.discount_pct or Decimal("0")
            try:
                d = Decimal(str(d))
            except Exception:
                d = Decimal("0")

            if d > 0:
                s += (gross * (d / Decimal("100")))
        return s

    @property
    def subtotal_net(self) -> Decimal:
        """Subtotal neto (bruto - descuentos por línea)."""
        return self.lines_subtotal_gross - self.lines_discount_total

    @property
    def extra_discount_amount(self) -> Decimal:
        """Monto del descuento extra (sobre subtotal_net)."""
        pct = self.extra_discount_pct or Decimal("0")
        try:
            pct = Decimal(str(pct))
        except Exception:
            pct = Decimal("0")

        if pct <= 0:
            return Decimal("0")
        if pct >= 100:
            return self.subtotal_net
        return self.subtotal_net * (pct / Decimal("100"))

    @property
    def total_final(self) -> Decimal:
        """Total final (subtotal_net - descuento extra)."""
        return self.subtotal_net - self.extra_discount_amount

    @property
    def total_clp(self) -> Decimal:
        """
        Total según líneas.
        - Si hay líneas: usa total_final (incluye descuento extra).
        - Si no hay líneas: cae a amount_clp.
        """
        lines_exist = self.lines.exists()
        if not lines_exist:
            return self.amount_clp or Decimal("0")
        return self.total_final

    # -----------------------------
    # Helpers
    # -----------------------------
    def ensure_default_dates(self):
        if not self.created_at:
            self.created_at = timezone.now()
        if not self.expires_at:
            self.expires_at = self.created_at + timezone.timedelta(days=30)

    def recalc_amount_from_lines(self):
        """
        Recalcula amount_clp desde las líneas.
        Guarda el TOTAL FINAL (subtotal neto - descuento extra).
        """
        if not self.lines.exists():
            # si no hay líneas, no pisa lo que ya tenga
            self.amount_clp = self.amount_clp or Decimal("0")
            return

        self.amount_clp = self.total_final

    def ensure_reference(self):
        if not self.pdf_reference and self.pk:
            # Ej: COT-000123
            self.pdf_reference = f"COT-{self.pk:06d}"

class QuoteLine(models.Model):
    quote = models.ForeignKey(
        Quote,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Cotización",
    )

    title = models.CharField("Título / ítem", max_length=255)
    qty = models.DecimalField("Cantidad", max_digits=18, decimal_places=2, default=1)
    unit_price_clp = models.DecimalField("Monto (CLP)", max_digits=18, decimal_places=2, default=0)

    # ✅ NUEVO: descuento por línea en %
    discount_pct = models.DecimalField(
        "Descuento (%)",
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Línea de cotización"
        verbose_name_plural = "Líneas de cotización"
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["quote"]),
        ]

    def __str__(self) -> str:
        return f"{self.title}"

    @property
    def line_total(self) -> Decimal:
        q = self.qty or Decimal("0")
        p = self.unit_price_clp or Decimal("0")
        gross = q * p

        d = self.discount_pct
        if d is None:
            d = Decimal("0")
        try:
            d = Decimal(str(d))
        except Exception:
            d = Decimal("0")

        if d <= 0:
            return gross
        if d >= 100:
            return Decimal("0")

        return gross * (Decimal("1") - (d / Decimal("100")))
    


# --- AUTO SYNC: actualizar valor del negocio al guardar una cotización ---
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Quote)
def sync_deal_value_from_quote(sender, instance: "Quote", **kwargs):
    """
    Cuando se guarda una cotización:
    - Si está relacionada a un negocio (deal), sincroniza Deal.value con el total real.
    Esto asegura que el valor del negocio se actualice automáticamente incluso si
    la cotización se guarda más de una vez en el flujo de creación (quote + líneas).
    """
    if not instance.deal_id:
        return

    try:
        # total_clp ya considera líneas y descuento extra si existen; si no hay líneas, cae a amount_clp
        new_value = instance.total_clp or Decimal("0")
    except Exception:
        new_value = instance.amount_clp or Decimal("0")

    # Actualiza el valor del negocio + actividad
    Deal.objects.filter(id=instance.deal_id).update(
        value=new_value,
        last_activity_at=timezone.now(),
    )
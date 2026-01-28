# finanzas_comercial/forms_tareas.py
import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .forms import comercial_users_qs
from .models import Company, Contact, Task


class _DTLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def format_value(self, value):
        if not value:
            return ""
        try:
            value = timezone.localtime(value) if timezone.is_aware(value) else value
            return value.strftime("%Y-%m-%dT%H:%M")
        except Exception:
            return super().format_value(value)


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "assigned_to",
            "contact",
            "company",
            "due_at",
            "description",
            "notify_by_email",
            "is_active",
        ]
        widgets = {
            "due_at": _DTLocalInput(),
            "description": forms.Textarea(attrs={"rows": 6}),
        }
        labels = {
            "title": "Título de la tarea",
            "assigned_to": "Asignar a",
            "contact": "Contacto asociado",
            "company": "Empresa asociada",
            "due_at": "Fecha de vencimiento (fecha y hora)",
            "description": "Descripción de la tarea",
            "notify_by_email": "Notificar por correo al crear",
            "is_active": "Activa",
        }

    def __init__(self, *args, **kwargs):
        # ✅ aceptar user sin romper BaseModelForm
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Assigned users
        self.fields["assigned_to"].queryset = comercial_users_qs().order_by(
            "first_name", "last_name", "email", "id"
        )

        # Company
        self.fields["company"].queryset = Company.objects.all().order_by("name", "id")
        self.fields["company"].empty_label = "---------"

        # Contact
        contacts_qs = (
            Contact.objects
            .select_related("company")
            .all()
            .order_by("first_name", "last_name", "id")
        )
        self.fields["contact"].queryset = contacts_qs
        self.fields["contact"].empty_label = "---------"

        # ✅ Mapa contacto -> empresa (para autoselección)
        # (usamos only para no traer todo)
        company_by_contact = {
            str(c.id): str(c.company_id)
            for c in contacts_qs.only("id", "company_id")
            if c.company_id
        }

        # ✅ NO CAMBIAR EL WIDGET del contacto (para no romper Select2/TomSelect/etc.)
        # Solo inyectamos data-company-map al widget actual
        self.fields["contact"].widget.attrs["data-company-map"] = json.dumps(company_by_contact)

        # ✅ FRONTEND: no permitir fecha menor a HOY (00:00)
        today = timezone.localdate()
        self.fields["due_at"].widget.attrs["min"] = today.strftime("%Y-%m-%dT00:00")

    def clean(self):
        cleaned = super().clean()

        due_at = cleaned.get("due_at")
        if due_at:
            due_local = timezone.localtime(due_at) if timezone.is_aware(due_at) else due_at
            if due_local.date() < timezone.localdate():
                self.add_error("due_at", ValidationError("No puedes crear tareas con vencimiento menor a hoy."))

        # Blindaje empresa desde contacto
        contact = cleaned.get("contact")
        company = cleaned.get("company")
        if contact and getattr(contact, "company_id", None):
            if (not company) or (company.id != contact.company_id):
                cleaned["company"] = contact.company

        return cleaned
# finanzas_comercial/forms_cotizaciones.py
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from .models import Contact, Deal, Quote, QuoteLine

User = get_user_model()


def commercial_users_qs():
    """
    Devuelve usuarios con rol comercial o jefe comercial.

    Soporta:
      1) Campo 'role' o 'rol' en User (si existe)
      2) Grupos: 'Comercial', 'Jefe Comercial', etc.
      3) Fallback: si el filtro queda vacío, devuelve usuarios activos (para no dejar selects vacíos)
    """
    qs = User.objects.filter(is_active=True).order_by("first_name", "last_name", "email", "id")

    # 1) Campo role/rol
    user_fields = {f.name for f in User._meta.get_fields() if hasattr(f, "name")}
    role_field = "role" if "role" in user_fields else ("rol" if "rol" in user_fields else None)

    role_values = [
        "comercial", "commercial",
        "jefe_comercial", "jefe comercial",
        "comercial_jefe", "comercial jefe",
        "commercial_manager",
    ]

    if role_field:
        q = Q()
        for rv in role_values:
            q |= Q(**{f"{role_field}__iexact": rv})
        filtered = qs.filter(q).distinct()
        return filtered if filtered.exists() else qs

    # 2) Grupos
    group_names = [
        "Comercial",
        "Jefe Comercial",
        "Comercial Jefe",
        "Commercial",
        "Commercial Manager",
        "commercial",
        "commercial_manager",
    ]

    try:
        q = Q()
        for g in group_names:
            q |= Q(groups__name__iexact=g)
        filtered = qs.filter(q).distinct()
        return filtered if filtered.exists() else qs
    except Exception:
        return qs


class QuoteForm(forms.ModelForm):
    """
    Form principal de Cotización.

    - En CREATE: status NO se pide (lo setea la vista).
    - Descuento extra final (opcional): nombre + porcentaje.
    - Moneda: CLP o USD.
    """

    class Meta:
        model = Quote
        fields = [
            "title",
            "status",
            "status_comment",
            "owner",
            "prepared_by",
            "deal",
            "contacts",
            "created_at",
            "expires_at",
            "comments",
            "purchase_conditions",
            "currency",
            "extra_discount_name",
            "extra_discount_pct",
            "is_active",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "w-full", "placeholder": "Ej: Presupuesto Reposición Piso..." }),
            "status": forms.Select(attrs={"class": "w-full"}),
            "status_comment": forms.Textarea(attrs={"class": "w-full", "rows": 2, "placeholder": "Comentario del estado (opcional)"}),

            "owner": forms.Select(attrs={"class": "w-full"}),
            "prepared_by": forms.Select(attrs={"class": "w-full"}),
            "deal": forms.Select(attrs={"class": "w-full"}),

            # ✅ contactos con checkboxes (sin shift/ctrl)
            "contacts": forms.CheckboxSelectMultiple(),

            "created_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "w-full"}),
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "w-full"}),

            "comments": forms.Textarea(attrs={"class": "w-full", "rows": 3}),
            "purchase_conditions": forms.Textarea(attrs={"class": "w-full", "rows": 3}),

            "currency": forms.Select(attrs={"class": "w-full"}),
            "extra_discount_name": forms.TextInput(attrs={"class": "w-full", "placeholder": "Ej: Descuento comercial"}),
            "extra_discount_pct": forms.NumberInput(attrs={"class": "w-full", "step": "0.01", "min": "0", "max": "100"}),

            "is_active": forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        inst = getattr(self, "instance", None)
        is_new = not (inst and getattr(inst, "pk", None))

        comercial_qs = commercial_users_qs()

        if "owner" in self.fields:
            self.fields["owner"].queryset = comercial_qs
            self.fields["owner"].required = False

        if "prepared_by" in self.fields:
            self.fields["prepared_by"].queryset = comercial_qs
            self.fields["prepared_by"].required = False

        if "deal" in self.fields:
            self.fields["deal"].queryset = Deal.objects.all().order_by("-created_at", "-id")
            self.fields["deal"].required = False

        if "contacts" in self.fields:
            self.fields["contacts"].queryset = Contact.objects.filter(is_active=True).order_by("-created_at", "-id")
            self.fields["contacts"].required = False
            self.fields["contacts"].help_text = "Selecciona 1 o 2 contactos."

        # ✅ CREATE: status NO se pide al usuario
        if is_new and "status" in self.fields:
            self.fields["status"].required = False
            self.fields["status"].initial = getattr(Quote.Status, "CREADA", Quote.Status.EN_MODIFICACION)
            self.fields["status"].widget = forms.HiddenInput()

        # defaults solo cuando es create
        if is_new:
            now = timezone.localtime(timezone.now())
            if "created_at" in self.fields and not self.initial.get("created_at"):
                self.initial["created_at"] = now.strftime("%Y-%m-%dT%H:%M")
            if "expires_at" in self.fields and not self.initial.get("expires_at"):
                exp = now + timezone.timedelta(days=30)
                self.initial["expires_at"] = exp.strftime("%Y-%m-%dT%H:%M")

            if user and user.is_authenticated:
                try:
                    if user in comercial_qs:
                        if "owner" in self.fields and not self.initial.get("owner"):
                            self.initial["owner"] = user.pk
                        if "prepared_by" in self.fields and not self.initial.get("prepared_by"):
                            self.initial["prepared_by"] = user.pk
                except Exception:
                    pass

        # defaults moneda si no viene
        if "currency" in self.fields:
            if not self.initial.get("currency") and not (inst and getattr(inst, "currency", None)):
                self.initial["currency"] = getattr(Quote.Currency, "CLP", "CLP")

    def clean_status(self):
        v = self.cleaned_data.get("status")
        if not v:
            return getattr(Quote.Status, "CREADA", Quote.Status.EN_MODIFICACION)
        return v

    def clean_contacts(self):
        contacts = self.cleaned_data.get("contacts")
        if not contacts:
            return contacts
        cnt = contacts.count() if hasattr(contacts, "count") else len(contacts)
        if cnt > 2:
            raise forms.ValidationError("Puedes seleccionar como máximo 2 contactos.")
        return contacts

    def clean_extra_discount_pct(self):
        v = self.cleaned_data.get("extra_discount_pct")
        if v in (None, ""):
            return Decimal("0")
        try:
            v = Decimal(str(v))
        except Exception:
            raise forms.ValidationError("Descuento inválido.")
        if v < 0:
            raise forms.ValidationError("El descuento no puede ser negativo.")
        if v > 100:
            raise forms.ValidationError("El descuento no puede ser mayor a 100%.")
        return v

    def clean(self):
        cleaned = super().clean()

        created_at = cleaned.get("created_at")
        expires_at = cleaned.get("expires_at")

        if created_at and not expires_at:
            cleaned["expires_at"] = created_at + timezone.timedelta(days=30)

        if created_at and expires_at and expires_at < created_at:
            self.add_error("expires_at", "La fecha de vencimiento no puede ser anterior a la fecha de creación.")

        # ✅ si no hay % o es 0, no mostrar nombre
        pct = cleaned.get("extra_discount_pct") or Decimal("0")
        name = (cleaned.get("extra_discount_name") or "").strip()
        try:
            pct = Decimal(str(pct))
        except Exception:
            pct = Decimal("0")
        if pct <= 0:
            cleaned["extra_discount_name"] = ""

        # ✅ si hay % > 0 pero no hay nombre, lo dejamos permitido (no obligamos)
        # (si quieres obligar nombre cuando hay %, me dices)

        return cleaned


class QuoteLineForm(forms.ModelForm):
    class Meta:
        model = QuoteLine
        fields = ["title", "qty", "unit_price_clp", "discount_pct", "sort_order"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "w-full", "placeholder": "Ítem / descripción"}),
            "qty": forms.NumberInput(attrs={"class": "w-full", "step": "0.01", "min": "0"}),
            "unit_price_clp": forms.NumberInput(attrs={"class": "w-full", "step": "0.01", "min": "0"}),

            "discount_pct": forms.NumberInput(attrs={"class": "w-full", "step": "0.01", "min": "0", "max": "100"}),

            "sort_order": forms.NumberInput(attrs={"class": "w-full", "min": "0"}),
        }

    def clean_qty(self):
        v = self.cleaned_data.get("qty")
        if v is None:
            return v
        try:
            v = Decimal(str(v))
        except Exception:
            raise forms.ValidationError("Cantidad inválida.")
        if v < 0:
            raise forms.ValidationError("La cantidad no puede ser negativa.")
        return v

    def clean_unit_price_clp(self):
        v = self.cleaned_data.get("unit_price_clp")
        if v is None:
            return v
        try:
            v = Decimal(str(v))
        except Exception:
            raise forms.ValidationError("Monto inválido.")
        if v < 0:
            raise forms.ValidationError("El monto no puede ser negativo.")
        return v

    def clean_discount_pct(self):
        v = self.cleaned_data.get("discount_pct")
        if v in (None, ""):
            return Decimal("0")
        try:
            v = Decimal(str(v))
        except Exception:
            raise forms.ValidationError("Descuento inválido.")
        if v < 0:
            raise forms.ValidationError("El descuento no puede ser negativo.")
        if v > 100:
            raise forms.ValidationError("El descuento no puede ser mayor a 100%.")
        return v


class BaseQuoteLineFormSet(BaseInlineFormSet):
    """
    Valida que exista al menos 1 línea válida (no marcada para borrar) y con título.
    """
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        count_ok = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            cd = form.cleaned_data or {}
            if cd.get("DELETE"):
                continue
            title = (cd.get("title") or "").strip()
            if title:
                count_ok += 1

        if count_ok == 0:
            raise forms.ValidationError("Debes agregar al menos 1 línea a la cotización.")


QuoteLineFormSet = inlineformset_factory(
    parent_model=Quote,
    model=QuoteLine,
    form=QuoteLineForm,
    formset=BaseQuoteLineFormSet,
    extra=1,
    can_delete=True,
)
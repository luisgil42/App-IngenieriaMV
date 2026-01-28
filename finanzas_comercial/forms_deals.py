from django import forms
from django.utils import timezone

from .forms import comercial_users_qs
from .models import Company, Deal, DealStage

DT_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"


class DealStageForm(forms.ModelForm):
    class Meta:
        model = DealStage
        fields = ["name", "sort_order", "is_active"]


class DealForm(forms.ModelForm):
    """
    Form completo (incluye etapa). Úsalo para EDITAR.
    """

    class Meta:
        model = Deal
        fields = [
            "name",
            "stage",
            "close_at",
            "company",
            "owner",
            "value",
            "is_active",
        ]
        widgets = {
            "close_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DT_LOCAL_FORMAT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["stage"].queryset = DealStage.objects.filter(is_active=True).order_by(
            "sort_order", "name", "id"
        )
        self.fields["company"].queryset = Company.objects.filter(is_active=True).order_by("name", "id")
        self.fields["owner"].queryset = comercial_users_qs().order_by("email")

        # ✅ Para que datetime-local precargue bien (YYYY-MM-DDTHH:MM)
        if self.instance and getattr(self.instance, "pk", None) and self.instance.close_at:
            dt = self.instance.close_at
            try:
                dt = timezone.localtime(dt)
            except Exception:
                pass
            self.initial["close_at"] = dt.strftime(DT_LOCAL_FORMAT)

    def clean_close_at(self):
        """
        Asegura parse correcto cuando viene del input datetime-local.
        Django normalmente lo maneja, pero dejamos esto robusto.
        """
        dt = self.cleaned_data.get("close_at")
        return dt


class DealCreateForm(forms.ModelForm):
    """
    Form para CREAR: NO pide etapa.
    La etapa se asigna automáticamente en la vista (En proceso).
    """

    class Meta:
        model = Deal
        fields = [
            "name",
            "close_at",
            "company",
            "owner",
            "value",
            "is_active",
        ]
        widgets = {
            "close_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DT_LOCAL_FORMAT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["company"].queryset = Company.objects.filter(is_active=True).order_by("name", "id")
        self.fields["owner"].queryset = comercial_users_qs().order_by("email")

        # (en create no hay instancia, pero queda por consistencia)
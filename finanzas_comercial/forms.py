from django import forms

from usuarios.models import Role, User

from .models import Company, Contact


def comercial_users_qs():
    # Usuarios activos con rol "Comercial"
    return (
        User.objects.filter(is_active=True, roles__name__iexact="Comercial")
        .distinct()
        .order_by("first_name", "last_name", "email")
    )


class ContactForm(forms.ModelForm):
    owner = forms.ModelChoiceField(
        queryset=comercial_users_qs(),
        required=False,
        label="Propietario del contacto",
    )

    class Meta:
        model = Contact
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "company",
            "job_title",
            "owner",
            "linkedin_url",
            "is_active",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "w-full"}),
            "last_name": forms.TextInput(attrs={"class": "w-full"}),
            "email": forms.EmailInput(attrs={"class": "w-full"}),
            "phone": forms.TextInput(attrs={"class": "w-full"}),
            "company": forms.Select(attrs={"class": "w-full"}),
            "job_title": forms.TextInput(attrs={"class": "w-full"}),
            "linkedin_url": forms.URLInput(attrs={"class": "w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Empresas activas primero
        self.fields["company"].queryset = Company.objects.filter(is_active=True).order_by("name", "id")

        # Refrescar propietarios (por si cambió data)
        self.fields["owner"].queryset = comercial_users_qs()



# finanzas_comercial/forms.py
from django import forms

from .models import Company


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "name", "rut", "city", "country_region", "sector",
            "phone", "logo", "is_active",
        ]
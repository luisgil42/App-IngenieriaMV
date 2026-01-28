from django import forms
from django.contrib.auth import authenticate

from .models import Role, User


class LoginForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        password = cleaned.get("password")
        if email and password:
            self.user = authenticate(self.request, username=email, password=password)
            if not self.user:
                raise forms.ValidationError("Credenciales inválidas o usuario bloqueado.")
        return cleaned

class OTPVerifyForm(forms.Form):
    token = forms.CharField(label="Código 2FA", max_length=12)

class TOTPSetupVerifyForm(forms.Form):
    token = forms.CharField(label="Código de verificación", max_length=12)

class UserForm(forms.ModelForm):
    password1 = forms.CharField(label="Contraseña", required=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Repetir contraseña", required=False, widget=forms.PasswordInput)
    roles = forms.ModelMultipleChoiceField(queryset=Role.objects.all(), required=False)

    class Meta:
        model = User
        fields = ["email", "full_name", "phone", "is_active", "is_staff", "force_2fa"]

    def clean(self):
        c = super().clean()
        p1 = c.get("password1")
        p2 = c.get("password2")
        if (p1 or p2) and p1 != p2:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        return c

    def save(self, commit=True):
        user = super().save(commit=False)
        if not user.username:
            user.username = user.email
        p1 = self.cleaned_data.get("password1")
        if p1:
            user.set_password(p1)
        if commit:
            user.save()
            self.save_m2m()
            user.roles.set(self.cleaned_data.get("roles"))
        return user

class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name", "description", "is_active", "require_2fa"]
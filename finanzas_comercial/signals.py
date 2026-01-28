# finanzas_comercial/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Company, Contact


@receiver(pre_save, sender=Contact)
def contact_pre_save_track_company(sender, instance: Contact, **kwargs):
    """
    Guardamos el company_id anterior para detectar cambios de empresa.
    """
    if not instance.pk:
        instance._old_company_id = None
        return

    try:
        old = Contact.objects.only("company_id").get(pk=instance.pk)
        instance._old_company_id = old.company_id
    except Contact.DoesNotExist:
        instance._old_company_id = None


@receiver(post_save, sender=Contact)
def contact_post_save_touch_company(sender, instance: Contact, created: bool, **kwargs):
    """
    Actualiza last_activity_at de la empresa:
    - Empresa actual (si existe)
    - Empresa anterior (si cambió)
    """
    now = timezone.now()

    # si el contacto tiene last_activity_at, úsalo; si no, ahora.
    activity_dt = instance.last_activity_at or now

    # 1) Empresa actual
    if instance.company_id:
        Company.objects.filter(id=instance.company_id).update(last_activity_at=activity_dt)

    # 2) Empresa anterior si cambió
    old_company_id = getattr(instance, "_old_company_id", None)
    if old_company_id and old_company_id != instance.company_id:
        Company.objects.filter(id=old_company_id).update(last_activity_at=now)
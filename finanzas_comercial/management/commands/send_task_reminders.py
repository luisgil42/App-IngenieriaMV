# finanzas_comercial/management/commands/send_task_reminders.py
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from finanzas_comercial.models import Task


def _send(to_email: str, subject: str, body: str, cc_email: str = ""):
    if not to_email:
        return
    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
        cc=[cc_email] if cc_email else None,
    )
    msg.send(fail_silently=True)


class Command(BaseCommand):
    help = "Envía recordatorios de tareas (diario vencimientos + lunes pendientes externos)."

    def handle(self, *args, **options):
        now = timezone.now()
        today = now.date()

        # =========================
        # 1) DIARIO: EN_PROCESO (NO PEND_EXTERNO)
        # - 1 día antes
        # - vencidas: todos los días
        # =========================
        tomorrow = today + timedelta(days=1)

        # Recordatorio 1 día antes
        soon_qs = Task.objects.select_related("assigned_to", "created_by").filter(
            is_active=True,
            status=Task.Status.EN_PROCESO,
            due_at__date=tomorrow,
        )

        for t in soon_qs:
            to_email = t.assigned_to.email
            cc_email = t.created_by.email if t.created_by_id else ""
            subject = f"Recordatorio: tarea #{t.pk} vence mañana"
            body = f"""Hola,

Tienes pendiente la tarea #{t.pk}: {t.title}

Vence mañana. Por favor revísala en el sistema MV Ingeniería.
Si ya la completaste, márcala como completada.

Saludos.
"""
            _send(to_email, subject, body, cc_email)

        # Recordatorio vencidas (todos los días)
        overdue_qs = Task.objects.select_related("assigned_to", "created_by").filter(
            is_active=True,
            status=Task.Status.EN_PROCESO,
            due_at__date__lt=today,
        )

        for t in overdue_qs:
            days = (today - t.due_at.date()).days if t.due_at else 0
            to_email = t.assigned_to.email
            cc_email = t.created_by.email if t.created_by_id else ""
            subject = f"Recordatorio: tarea #{t.pk} vencida"
            body = f"""Hola,

Tienes pendiente la tarea #{t.pk}: {t.title}

Está vencida hace {days} día(s).
Si ya la completaste, márcala como completada en el sistema.
Si no, por favor gestionarla a la brevedad.

Saludos.
"""
            _send(to_email, subject, body, cc_email)

        # =========================
        # 2) SEMANAL: LUNES PEND_EXTERNO (resumen por asignado)
        # =========================
        if now.weekday() == 0:  # lunes
            pend_qs = Task.objects.select_related("assigned_to").filter(
                is_active=True,
                status=Task.Status.PEND_EXTERNO,
            ).order_by("assigned_to_id", "-created_at")

            by_user = {}
            for t in pend_qs:
                by_user.setdefault(t.assigned_to_id, []).append(t)

            for user_id, tasks in by_user.items():
                u = tasks[0].assigned_to
                to_email = u.email
                subject = "Resumen semanal: tareas pendientes por persona externa"
                lines = []
                for t in tasks:
                    obs = t.status_comment or "(sin observación)"
                    lines.append(f"- #{t.pk} {t.title} | Obs: {obs}")
                body = f"""Hola,

Tienes estas tareas en estatus "Pendiente por persona externa":

{chr(10).join(lines)}

Recomendación: ponte en contacto con la persona externa para agilizar el proceso,
o confirma una fecha de entrega/solución.

Saludos.
"""
                _send(to_email, subject, body)

        self.stdout.write(self.style.SUCCESS("OK - recordatorios ejecutados"))
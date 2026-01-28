# finanzas_comercial/views_tareas.py
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms_tareas import TaskForm
from .models import Task, TaskAttachment
from .permissions_ui import ensure_finanzas_access


def _ensure_access(request) -> bool:
    return ensure_finanzas_access(request)


def _abs_url(request, url: str) -> str:
    try:
        return request.build_absolute_uri(url)
    except Exception:
        base = getattr(settings, "SITE_URL", "").rstrip("/")
        return f"{base}{url}" if base else url


def _send_task_assigned_email(request, task: Task):
    if not task.notify_by_email:
        return

    to_email = getattr(task.assigned_to, "email", "") or ""
    cc_email = getattr(task.created_by, "email", "") or ""
    if not to_email:
        return

    subject = f"Tarea asignada Ingeniería MN #{task.pk}"

    due_txt = "--"
    if task.due_at:
        due_local = timezone.localtime(task.due_at) if timezone.is_aware(task.due_at) else task.due_at
        due_txt = due_local.strftime("%d-%m-%Y %H:%M")

    created_by_name = task.created_by.get_full_name() or task.created_by.email or str(task.created_by)
    assigned_name = task.assigned_to.get_full_name() or task.assigned_to.email or str(task.assigned_to)

    contact_txt = task.contact.full_name if task.contact_id else "--"
    company_txt = task.company.name if task.company_id else "--"

    links = []
    for a in task.attachments.all().order_by("-uploaded_at", "-id"):
        try:
            links.append(f"- {a.original_name or a.file.name}: {_abs_url(request, a.file.url)}")
        except Exception:
            pass
    links_block = "\n".join(links) if links else "- (Sin documentos)"

    body = f"""Hola {assigned_name},

Se te ha asignado una tarea en MV Ingeniería.

Tarea: #{task.pk} - {task.title}
Asignada por: {created_by_name}
Contacto asociado: {contact_txt}
Empresa asociada: {company_txt}
Vencimiento: {due_txt}

Descripción:
{task.description or "-"}

Documentos:
{links_block}

Por favor ingresa al sistema para gestionarla.

Saludos.
"""

    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
        cc=[cc_email] if cc_email else None,
    )
    msg.send(fail_silently=True)


@login_required
def task_list(request):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    q = (request.GET.get("q") or "").strip()
    assigned = (request.GET.get("assigned") or "").strip()
    active = (request.GET.get("active") or "").strip()

    # ✅ cantidad por página
    cantidad_raw = (request.GET.get("cantidad") or "20").strip()
    try:
        cantidad = int(cantidad_raw)
    except Exception:
        cantidad = 20
    if cantidad not in (5, 10, 20, 50, 100):
        cantidad = 20

    last_assigned_subq = (
        Task.objects
        .filter(assigned_to_id=OuterRef("assigned_to_id"))
        .order_by("-created_at", "-id")
        .values("created_at")[:1]
    )

    qs = (
        Task.objects
        .select_related("assigned_to", "created_by", "contact", "company")
        .prefetch_related("attachments")
        .annotate(last_contact_at=Subquery(last_assigned_subq))
        .all()
        .order_by("-created_at", "-id")
    )

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(description__icontains=q) |
            Q(company__name__icontains=q) |
            Q(contact__first_name__icontains=q) |
            Q(contact__last_name__icontains=q) |
            Q(assigned_to__email__icontains=q) |
            Q(assigned_to__first_name__icontains=q) |
            Q(assigned_to__last_name__icontains=q) |
            Q(created_by__email__icontains=q) |
            Q(created_by__first_name__icontains=q) |
            Q(created_by__last_name__icontains=q)
        )

    if assigned.isdigit():
        qs = qs.filter(assigned_to_id=int(assigned))

    if active == "1":
        qs = qs.filter(is_active=True)
    elif active == "0":
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, cantidad)
    page_number = request.GET.get("page") or "1"
    pagina = paginator.get_page(page_number)

    base_params = request.GET.copy()
    if "page" in base_params:
        base_params.pop("page")
    base_qs = base_params.urlencode()

    # ✅ IMPORTANTE: pasar user al form (por querysets/permissions)
    # task_list (cambia solo esta línea)
    form = TaskForm(user=request.user)
    assigned_users = form.fields["assigned_to"].queryset

    return render(request, "finanzas_comercial/task_list.html", {
        "pagina": pagina,
        "base_qs": base_qs,
        "cantidad": str(cantidad),

        "q": q,
        "assigned": assigned,
        "active": active,
        "assigned_users": assigned_users,

        "status_choices": Task.Status.choices,
        "STATUS_PEND_EXTERNO": Task.Status.PEND_EXTERNO,  # ✅ nuevo
        "STATUS_COMPLETADA": Task.Status.COMPLETADA, 
        "now": timezone.now(),
    })


@login_required
def task_create(request):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    # ✅ IMPORTANTE: pasar user al form
    form = TaskForm(request.POST or None, request.FILES or None, user=request.user)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            obj: Task = form.save(commit=False)
            obj.created_by = request.user
            obj.status = Task.Status.EN_PROCESO
            obj.completed_at = None

            # ✅ Blindaje: empresa siempre desde el contacto
            if obj.contact_id and obj.contact and obj.contact.company_id:
                obj.company_id = obj.contact.company_id

            obj.save()

            files = request.FILES.getlist("attachments")
            for f in files:
                if not f:
                    continue
                TaskAttachment.objects.create(
                    task=obj,
                    file=f,
                    original_name=getattr(f, "name", "") or "",
                    content_type=getattr(f, "content_type", "") or "",
                    size_bytes=getattr(f, "size", 0) or 0,
                    uploaded_by=request.user,
                )

        try:
            obj = (
                Task.objects
                .select_related("assigned_to", "created_by", "contact", "company")
                .prefetch_related("attachments")
                .get(pk=obj.pk)
            )
            _send_task_assigned_email(request, obj)
        except Exception:
            pass

        messages.success(request, f"✅ Tarea creada (#{obj.pk}).")
        return redirect("finanzas_comercial:task_list")

    return render(request, "finanzas_comercial/task_form.html", {
        "title": "Crear tarea",
        "form": form,
        "is_edit": False,
        "obj": None,
    })


@login_required
def task_edit(request, pk: int):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    obj = get_object_or_404(
        Task.objects.select_related("assigned_to", "created_by", "contact", "company").prefetch_related("attachments"),
        pk=pk,
    )

    # ✅ IMPORTANTE: pasar user al form
    form = TaskForm(request.POST or None, request.FILES or None, instance=obj, user=request.user)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            edited: Task = form.save(commit=False)

            # ✅ Blindaje: empresa siempre desde el contacto
            if edited.contact_id and edited.contact and edited.contact.company_id:
                edited.company_id = edited.contact.company_id

            edited.save()

            files = request.FILES.getlist("attachments")
            for f in files:
                if not f:
                    continue
                TaskAttachment.objects.create(
                    task=edited,
                    file=f,
                    original_name=getattr(f, "name", "") or "",
                    content_type=getattr(f, "content_type", "") or "",
                    size_bytes=getattr(f, "size", 0) or 0,
                    uploaded_by=request.user,
                )

        messages.success(request, f"✅ Tarea actualizada (#{obj.pk}).")
        return redirect("finanzas_comercial:task_list")

    return render(request, "finanzas_comercial/task_form.html", {
        "title": "Editar tarea",
        "form": form,
        "is_edit": True,
        "obj": obj,
    })


@login_required
def task_delete(request, pk: int):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    obj = get_object_or_404(Task, pk=pk)

    if request.method != "POST":
        messages.error(request, "Acción inválida.")
        return redirect("finanzas_comercial:task_list")

    try:
        obj.delete()
        messages.success(request, "✅ Tarea eliminada.")
    except Exception:
        messages.error(request, "No se pudo eliminar la tarea.")

    return redirect("finanzas_comercial:task_list")


@login_required
def task_update_status(request, pk: int):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    obj = get_object_or_404(Task, pk=pk)

    if request.method != "POST":
        messages.error(request, "Acción inválida.")
        return redirect("finanzas_comercial:task_list")

    new_status = (request.POST.get("status") or "").strip()
    comment = (request.POST.get("comment") or "").strip()

    valid = {c[0] for c in Task.Status.choices}
    if new_status not in valid:
        messages.error(request, "Estatus inválido.")
        return redirect("finanzas_comercial:task_list")

    if new_status == Task.Status.PEND_EXTERNO and not comment:
        messages.error(request, "Para 'Pendiente por persona externa' debes ingresar un comentario obligatorio.")
        return redirect("finanzas_comercial:task_list")

    with transaction.atomic():
        obj.status = new_status

        if new_status == Task.Status.COMPLETADA:
            obj.completed_at = timezone.now()
            if comment:
                obj.status_comment = comment
        elif new_status == Task.Status.PEND_EXTERNO:
            obj.completed_at = None
            obj.status_comment = comment
        else:
            obj.completed_at = None

        obj.save(update_fields=["status", "status_comment", "completed_at", "updated_at"])

    messages.success(request, "✅ Estatus actualizado.")
    return redirect("finanzas_comercial:task_list")
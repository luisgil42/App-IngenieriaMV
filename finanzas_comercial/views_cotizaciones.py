# finanzas_comercial/views_cotizaciones.py
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from .forms_cotizaciones import (QuoteForm, QuoteLineFormSet,
                                 commercial_users_qs)
from .models import Quote  # ✅ TODO está en models.py
from .permissions_ui import ensure_finanzas_access


def _ensure_access(request) -> bool:
    return ensure_finanzas_access(request)


def _abs_url(request, url: str) -> str:
    try:
        return request.build_absolute_uri(url)
    except Exception:
        base = getattr(settings, "SITE_URL", "").rstrip("/")
        return f"{base}{url}" if base else url


def _is_ajax(request) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _to_decimal(v) -> Decimal:
    try:
        if v is None:
            return Decimal("0")
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def _pct_to_decimal(pct) -> Decimal:
    p = _to_decimal(pct)
    if p <= 0:
        return Decimal("0")
    return (p / Decimal("100"))


def _default_created_status() -> str:
    """
    Estado por defecto al CREAR:
    - Si existe Quote.Status.CREADA => usarlo
    - si no, fallback a EN_MODIFICACION
    """
    try:
        return getattr(Quote.Status, "CREADA")
    except Exception:
        return Quote.Status.EN_MODIFICACION


def _line_calc_any(ln) -> dict:
    """
    Normaliza una línea a dict, y calcula:
    - gross = qty * unit_price_clp
    - discount = gross * (discount_pct/100)
    - net = gross - discount

    Soporta:
    - dict preview {title, qty, unit_price_clp, sort_order, discount_pct}
    - model line con attrs .title .qty .unit_price_clp .discount_pct
    """
    if isinstance(ln, dict):
        title = (ln.get("title") or "").strip()
        qty = _to_decimal(ln.get("qty"))
        unit = _to_decimal(ln.get("unit_price_clp"))
        discount_pct = _to_decimal(ln.get("discount_pct"))
        sort_order = ln.get("sort_order") or 0
    else:
        title = (getattr(ln, "title", "") or "").strip()
        qty = _to_decimal(getattr(ln, "qty", 0))
        unit = _to_decimal(getattr(ln, "unit_price_clp", 0))
        discount_pct = _to_decimal(getattr(ln, "discount_pct", 0))
        sort_order = getattr(ln, "sort_order", 0) or 0

    gross = qty * unit
    disc = gross * _pct_to_decimal(discount_pct)
    net = gross - disc

    return {
        "title": title,
        "qty": qty,
        "unit_price_clp": unit,
        "discount_pct": discount_pct,
        "sort_order": sort_order,
        "line_gross": gross,
        "line_discount": disc,
        "line_net": net,       # ✅ neto (para subtotal net)
        "line_total": net,     # ✅ compatibilidad: line_total = net
    }


def _calc_totals_from_lines(lines_any) -> dict:
    """
    Devuelve:
      - gross_total: suma qty*unit (sin descuentos)
      - lines_discount_total: suma descuentos por línea
      - subtotal_net: gross_total - lines_discount_total
    """
    gross_total = Decimal("0")
    lines_discount_total = Decimal("0")
    subtotal_net = Decimal("0")

    for ln in lines_any or []:
        c = _line_calc_any(ln)
        gross_total += _to_decimal(c["line_gross"])
        lines_discount_total += _to_decimal(c["line_discount"])
        subtotal_net += _to_decimal(c["line_net"])

    return {
        "gross_total": gross_total,
        "lines_discount_total": lines_discount_total,
        "subtotal_net": subtotal_net,
    }




def _quote_company_context(quote: Quote) -> dict:
    """
    Datos de cabecera (lado derecho) para el PDF.
    """
    default_company = {
        "name": "INGENIERIA Y CONSTRUCCION MV LTDA",
        "address_1": "Guardia Vieja 202 OF 902",
        "address_2": "Providencia",
        "city": "Santiago de Chile, Región Metropolitana",
        "country": "CHILE",
        "prepared_role": "Sales manager",
        "prepared_email": "ventas@ingenieriamv.cl",
        "prepared_phone": "+56978999600",
        "website": "",
        "prepared_name": "-",
        "logo_static": "core/images/logo_mv.png",
        "logo_w": 86,
        "logo_h": 86,
    }

    override = getattr(settings, "QUOTE_COMPANY", None) or {}
    company = {**default_company, **override}

    pb = getattr(quote, "prepared_by", None)
    if pb:
        full_name = ""
        try:
            full_name = pb.get_full_name() or ""
        except Exception:
            full_name = ""
        company["prepared_name"] = full_name or getattr(pb, "username", "") or str(pb)

        if not override.get("prepared_email"):
            company["prepared_email"] = getattr(pb, "email", "") or company.get("prepared_email", "")

        if not override.get("prepared_phone"):
            company["prepared_phone"] = (
                getattr(pb, "phone", "") or getattr(pb, "telefono", "") or company.get("prepared_phone", "")
            )

    return company

def _currency_meta(quote: Quote) -> dict:
    cur = (getattr(quote, "currency", None) or "CLP").upper()
    if cur == "USD":
        return {"code": "USD", "symbol": "US$", "decimals": 2}
    return {"code": "CLP", "symbol": "$", "decimals": 0}


def _render_quote_html(request, quote: Quote, preview_lines=None, preview_contacts=None) -> str:
    """
    Renderiza HTML para preview/PDF usando template.
    """
    # líneas
    if preview_lines is not None:
        raw_lines = preview_lines
    else:
        raw_lines = list(quote.lines.all()) if getattr(quote, "pk", None) else []

    # normalizar + cálculo
    lines = []
    for ln in raw_lines:
        c = _line_calc_any(ln)
        if c["title"]:
            lines.append(c)
    lines.sort(key=lambda x: (x.get("sort_order", 0), x.get("title", "")))

    # contactos
    if preview_contacts is not None:
        contacts = list(preview_contacts)
    else:
        contacts = list(quote.contacts.all()) if getattr(quote, "pk", None) else []

    # totales líneas
    totals = _calc_totals_from_lines(lines)
    gross_total = totals["gross_total"]
    lines_discount_total = totals["lines_discount_total"]
    subtotal_net = totals["subtotal_net"]  # ✅ este es el “Subtotal por única vez”

    # descuento extra final (opcional)
    extra_pct = _to_decimal(getattr(quote, "extra_discount_pct", 0))
    extra_name = (getattr(quote, "extra_discount_name", "") or "").strip()
    extra_amount = Decimal("0")
    if extra_pct > 0:
        if extra_pct >= 100:
            extra_amount = subtotal_net
        else:
            extra_amount = subtotal_net * (extra_pct / Decimal("100"))

    total_final = subtotal_net - extra_amount

    company = _quote_company_context(quote)
    curmeta = _currency_meta(quote)

    return render_to_string(
        "finanzas_comercial/quote_pdf.html",
        {
            "quote": quote,
            "lines": lines,
            "contacts": contacts,

            # ✅ para el PDF con la nueva lógica
            "gross_total": gross_total,
            "lines_discount_total": lines_discount_total,
            "subtotal_net": subtotal_net,
            "extra_discount_name": extra_name,
            "extra_discount_pct": extra_pct,
            "extra_discount_amount": extra_amount,
            "total_final": total_final,

            # moneda
            "currency_code": curmeta["code"],
            "currency_symbol": curmeta["symbol"],
            "currency_decimals": curmeta["decimals"],

            "company": company,
            "now": timezone.now(),
            "request": request,
        },
        request=request,
    )


def _generate_pdf_bytes_from_html(request, html: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception:
        raise RuntimeError(
            "WeasyPrint no está instalado. Instala: pip install weasyprint (y dependencias del sistema)."
        )
    base_url = request.build_absolute_uri("/")
    return HTML(string=html, base_url=base_url).write_pdf()




@login_required
def quote_list(request):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    q = (request.GET.get("q") or "").strip()
    owner = (request.GET.get("owner") or "").strip()
    status = (request.GET.get("status") or "").strip()
    active = (request.GET.get("active") or "").strip()

    cantidad_raw = (request.GET.get("cantidad") or "20").strip()
    try:
        cantidad = int(cantidad_raw)
    except Exception:
        cantidad = 20
    if cantidad not in (5, 10, 20, 50, 100):
        cantidad = 20

    qs = (
        Quote.objects
        .select_related("owner", "prepared_by", "deal", "created_by")
        .prefetch_related("contacts", "lines")
        .all()
        .order_by("-created_at", "-id")
    )

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(status_comment__icontains=q) |
            Q(pdf_reference__icontains=q) |
            Q(deal__name__icontains=q) |
            Q(owner__email__icontains=q) |
            Q(owner__first_name__icontains=q) |
            Q(owner__last_name__icontains=q)
        )

    if owner.isdigit():
        qs = qs.filter(owner_id=int(owner))

    valid_status = {c[0] for c in Quote.Status.choices}
    if status in valid_status:
        qs = qs.filter(status=status)

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

    commercial_users = commercial_users_qs()

    return render(request, "finanzas_comercial/quote_list.html", {
        "pagina": pagina,
        "base_qs": base_qs,
        "cantidad": str(cantidad),

        "q": q,
        "owner": owner,
        "status": status,
        "active": active,

        "commercial_users": commercial_users,
        "status_choices": Quote.Status.choices,

        "STATUS_ENVIADA": Quote.Status.ENVIADA,
        "STATUS_APROBADA": Quote.Status.APROBADA,
        "STATUS_RECHAZADA": Quote.Status.RECHAZADA,
        "STATUS_EN_MODIFICACION": Quote.Status.EN_MODIFICACION,

        "now": timezone.now(),
    })


@login_required
def quote_create(request):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    form = QuoteForm(request.POST or None, user=request.user)
    formset = QuoteLineFormSet(request.POST or None, prefix="lines")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()  # "preview" | "save" | "back"

        if action == "back":
            return render(request, "finanzas_comercial/quote_form.html", {
                "title": "Crear cotización",
                "form": form,
                "formset": formset,
                "is_edit": False,
                "obj": None,
            })

        if form.is_valid() and formset.is_valid():
            obj: Quote = form.save(commit=False)
            obj.created_by = request.user

            # ✅ estado por defecto al crear
            obj.status = _default_created_status()

            # fechas default
            if hasattr(obj, "ensure_default_dates"):
                obj.ensure_default_dates()
            else:
                if not getattr(obj, "created_at", None):
                    obj.created_at = timezone.now()
                if not getattr(obj, "expires_at", None):
                    obj.expires_at = timezone.now() + timezone.timedelta(days=30)

            # preview lines
            preview_lines = []
            for f in formset.forms:
                cd = getattr(f, "cleaned_data", None) or {}
                if not cd or cd.get("DELETE"):
                    continue
                title = (cd.get("title") or "").strip()
                if not title:
                    continue
                preview_lines.append({
                    "title": title,
                    "qty": cd.get("qty") or Decimal("0"),
                    "unit_price_clp": cd.get("unit_price_clp") or Decimal("0"),
                    "discount_pct": cd.get("discount_pct") or Decimal("0"),
                    "sort_order": cd.get("sort_order") or 0,
                })
            preview_lines.sort(key=lambda x: (x.get("sort_order", 0), x.get("title", "")))

            preview_contacts = form.cleaned_data.get("contacts")

            if action == "preview":
                html = _render_quote_html(
                    request,
                    obj,
                    preview_lines=preview_lines,
                    preview_contacts=preview_contacts,
                )
                return render(request, "finanzas_comercial/quote_preview.html", {
                    "title": "Previsualizar cotización",
                    "preview_html": html,
                    "is_edit": False,
                    "obj": None,
                })

            if action == "save":
                with transaction.atomic():
                    obj.save()
                    form.save_m2m()

                    lines = formset.save(commit=False)
                    for ln in lines:
                        ln.quote = obj
                        ln.save()
                    for ln in formset.deleted_objects:
                        ln.delete()

                    if hasattr(obj, "ensure_reference"):
                        obj.ensure_reference()
                        obj.save(update_fields=["pdf_reference", "updated_at"])

                    # ✅ amount_clp = total_final (subtotal_net - extra)
                    totals = _calc_totals_from_lines(list(obj.lines.all()))
                    subtotal_net = totals["subtotal_net"]

                    extra_pct = _to_decimal(getattr(obj, "extra_discount_pct", 0))
                    extra_amount = Decimal("0")
                    if extra_pct > 0:
                        if extra_pct >= 100:
                            extra_amount = subtotal_net
                        else:
                            extra_amount = subtotal_net * (extra_pct / Decimal("100"))

                    obj.amount_clp = subtotal_net - extra_amount
                    obj.save(update_fields=["amount_clp", "updated_at"])

                    html = _render_quote_html(request, obj)
                    try:
                        pdf_bytes = _generate_pdf_bytes_from_html(request, html)
                        filename = f"{obj.pdf_reference or f'COT-{obj.pk:06d}'}.pdf"
                        obj.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
                        obj.save(update_fields=["pdf_file", "updated_at"])
                    except Exception as e:
                        messages.warning(request, f"Se guardó la cotización, pero no se pudo generar el PDF: {e}")

                messages.success(request, f"✅ Cotización creada (#{obj.pk}).")
                return redirect("finanzas_comercial:quote_list")

        messages.error(request, "Revisa el formulario: hay errores.")

    return render(request, "finanzas_comercial/quote_form.html", {
        "title": "Crear cotización",
        "form": form,
        "formset": formset,
        "is_edit": False,
        "obj": None,
    })

@login_required
def quote_edit(request, pk: int):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    obj = get_object_or_404(
        Quote.objects.select_related("owner", "prepared_by", "deal", "created_by").prefetch_related("contacts", "lines"),
        pk=pk,
    )

    form = QuoteForm(request.POST or None, instance=obj, user=request.user)
    formset = QuoteLineFormSet(request.POST or None, instance=obj, prefix="lines")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "back":
            return render(request, "finanzas_comercial/quote_form.html", {
                "title": "Editar cotización",
                "form": form,
                "formset": formset,
                "is_edit": True,
                "obj": obj,
            })

        if form.is_valid() and formset.is_valid():
            edited: Quote = form.save(commit=False)

            # fechas default
            if hasattr(edited, "ensure_default_dates"):
                edited.ensure_default_dates()
            else:
                if not getattr(edited, "created_at", None):
                    edited.created_at = timezone.now()
                if not getattr(edited, "expires_at", None):
                    edited.expires_at = timezone.now() + timezone.timedelta(days=30)

            preview_lines = []
            for f in formset.forms:
                cd = getattr(f, "cleaned_data", None) or {}
                if not cd or cd.get("DELETE"):
                    continue
                title = (cd.get("title") or "").strip()
                if not title:
                    continue
                preview_lines.append({
                    "title": title,
                    "qty": cd.get("qty") or Decimal("0"),
                    "unit_price_clp": cd.get("unit_price_clp") or Decimal("0"),
                    "discount_pct": cd.get("discount_pct") or Decimal("0"),
                    "sort_order": cd.get("sort_order") or 0,
                })
            preview_lines.sort(key=lambda x: (x.get("sort_order", 0), x.get("title", "")))

            preview_contacts = form.cleaned_data.get("contacts")

            if action == "preview":
                html = _render_quote_html(
                    request,
                    edited,
                    preview_lines=preview_lines,
                    preview_contacts=preview_contacts,
                )
                return render(request, "finanzas_comercial/quote_preview.html", {
                    "title": "Previsualizar cotización",
                    "preview_html": html,
                    "is_edit": True,
                    "obj": obj,
                })

            if action == "save":
                with transaction.atomic():
                    edited.save()
                    form.save_m2m()
                    formset.save()

                    if hasattr(edited, "ensure_reference"):
                        edited.ensure_reference()
                        edited.save(update_fields=["pdf_reference", "updated_at"])

                    # ✅ amount_clp = total_final (subtotal_net - extra)
                    totals = _calc_totals_from_lines(list(edited.lines.all()))
                    subtotal_net = totals["subtotal_net"]

                    extra_pct = _to_decimal(getattr(edited, "extra_discount_pct", 0))
                    extra_amount = Decimal("0")
                    if extra_pct > 0:
                        if extra_pct >= 100:
                            extra_amount = subtotal_net
                        else:
                            extra_amount = subtotal_net * (extra_pct / Decimal("100"))

                    edited.amount_clp = subtotal_net - extra_amount
                    edited.save(update_fields=["amount_clp", "updated_at"])

                    html = _render_quote_html(request, edited)
                    try:
                        pdf_bytes = _generate_pdf_bytes_from_html(request, html)
                        filename = f"{edited.pdf_reference or f'COT-{edited.pk:06d}'}.pdf"
                        edited.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
                        edited.save(update_fields=["pdf_file", "updated_at"])
                    except Exception as e:
                        messages.warning(request, f"Se guardó la cotización, pero no se pudo regenerar el PDF: {e}")

                messages.success(request, f"✅ Cotización actualizada (#{obj.pk}).")
                return redirect("finanzas_comercial:quote_list")

        messages.error(request, "Revisa el formulario: hay errores.")

    return render(request, "finanzas_comercial/quote_form.html", {
        "title": "Editar cotización",
        "form": form,
        "formset": formset,
        "is_edit": True,
        "obj": obj,
    })


@login_required
def quote_delete(request, pk: int):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    obj = get_object_or_404(Quote, pk=pk)

    if request.method != "POST":
        messages.error(request, "Acción inválida.")
        return redirect("finanzas_comercial:quote_list")

    try:
        obj.delete()
        messages.success(request, "✅ Cotización eliminada.")
    except Exception:
        messages.error(request, "No se pudo eliminar la cotización.")

    return redirect("finanzas_comercial:quote_list")


@login_required
def quote_duplicate(request, pk: int):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    obj = get_object_or_404(
        Quote.objects
        .select_related("owner", "prepared_by", "deal", "created_by")
        .prefetch_related("contacts", "lines"),
        pk=pk,
    )

    with transaction.atomic():
        # ✅ crear cotización nueva
        new = Quote.objects.create(
            title=f"{obj.title} (copia)",
            status=Quote.Status.EN_MODIFICACION,
            status_comment="",

            # esto lo recalculamos abajo sí o sí
            amount_clp=Decimal("0"),

            owner=obj.owner,
            prepared_by=obj.prepared_by,
            deal=obj.deal,

            created_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(days=30),

            # ✅ copiar campos extra
            comments=getattr(obj, "comments", ""),
            purchase_conditions=getattr(obj, "purchase_conditions", ""),

            currency=getattr(obj, "currency", "CLP"),

            # ✅ copiar descuento extra final
            extra_discount_name=getattr(obj, "extra_discount_name", "") or "",
            extra_discount_pct=_to_decimal(getattr(obj, "extra_discount_pct", 0)),

            is_active=obj.is_active,
            created_by=request.user,
        )

        # ✅ copiar contactos
        new.contacts.set(list(obj.contacts.all()))

        # ✅ copiar líneas
        for ln in obj.lines.all().order_by("sort_order", "id"):
            payload = {
                "title": getattr(ln, "title", "") or "",
                "qty": getattr(ln, "qty", 0) or 0,
                "unit_price_clp": getattr(ln, "unit_price_clp", 0) or 0,
                "sort_order": getattr(ln, "sort_order", 0) or 0,
            }
            # ✅ copiar descuento por línea si existe
            if hasattr(ln, "discount_pct"):
                payload["discount_pct"] = getattr(ln, "discount_pct", 0) or 0

            new.lines.create(**payload)

        # ✅ asegurar referencia
        if hasattr(new, "ensure_reference"):
            new.ensure_reference()
            new.save(update_fields=["pdf_reference", "updated_at"])

        # ✅ recalcular amount_clp = subtotal_net - extra_amount
        totals = _calc_totals_from_lines(list(new.lines.all()))
        subtotal_net = totals["subtotal_net"]

        extra_pct = _to_decimal(getattr(new, "extra_discount_pct", 0))
        extra_amount = Decimal("0")
        if extra_pct > 0:
            if extra_pct >= 100:
                extra_amount = subtotal_net
            else:
                extra_amount = subtotal_net * (extra_pct / Decimal("100"))

        new.amount_clp = subtotal_net - extra_amount
        new.save(update_fields=["amount_clp", "updated_at"])

        # ✅ generar PDF
        html = _render_quote_html(request, new)
        try:
            pdf_bytes = _generate_pdf_bytes_from_html(request, html)
            filename = f"{new.pdf_reference or f'COT-{new.pk:06d}'}.pdf"
            new.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
            new.save(update_fields=["pdf_file", "updated_at"])
        except Exception as e:
            messages.warning(request, f"Duplicada, pero no se pudo generar PDF: {e}")

    messages.success(request, f"✅ Cotización duplicada (#{new.pk}).")
    return redirect("finanzas_comercial:quote_edit", pk=new.pk)


@login_required
def quote_update_status(request, pk: int):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    obj = get_object_or_404(Quote, pk=pk)

    if request.method != "POST":
        if _is_ajax(request):
            return JsonResponse({"ok": False, "error": "Método inválido."}, status=405)
        messages.error(request, "Acción inválida.")
        return redirect("finanzas_comercial:quote_list")

    new_status = (request.POST.get("status") or "").strip()
    comment = (request.POST.get("comment") or "").strip()

    valid = {c[0] for c in Quote.Status.choices}
    if new_status not in valid:
        if _is_ajax(request):
            return JsonResponse({"ok": False, "error": "Estado inválido."}, status=400)
        messages.error(request, "Estado inválido.")
        return redirect("finanzas_comercial:quote_list")

    with transaction.atomic():
        obj.status = new_status
        # comentario opcional para todos los estados
        if comment:
            obj.status_comment = comment
        obj.save(update_fields=["status", "status_comment", "updated_at"])

    if _is_ajax(request):
        return JsonResponse({
            "ok": True,
            "status": obj.status,
            "status_display": obj.get_status_display(),
            "status_comment": obj.status_comment,
        })

    messages.success(request, "✅ Estado actualizado.")
    return redirect("finanzas_comercial:quote_list")


@login_required
def quote_pdf_download(request, pk: int):
    if not _ensure_access(request):
        return redirect("core:dashboard")

    obj = get_object_or_404(Quote, pk=pk)

    if not getattr(obj, "pdf_file", None):
        raise Http404("No existe PDF para esta cotización.")

    try:
        filename = (obj.pdf_reference or f"cotizacion_{obj.pk}")
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"

        return FileResponse(
            obj.pdf_file.open("rb"),
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )
    except Exception:
        raise Http404("No se pudo abrir el PDF.")
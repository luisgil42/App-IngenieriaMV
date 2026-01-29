# core/views.py
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, F, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone


def _find_field_name(model_cls, candidates: list[str]) -> str | None:
    for name in candidates:
        try:
            model_cls._meta.get_field(name)
            return name
        except Exception:
            continue
    return None


def _build_text_lookup_for_field(model_cls, field_name: str) -> str | None:
    """
    Devuelve lookup para icontains:
      - Char/Text -> "<field>__icontains"
      - FK -> "<field>__<attr>__icontains" donde attr es name/slug/code/etc.
    """
    try:
        field = model_cls._meta.get_field(field_name)
    except Exception:
        return None

    if isinstance(field, (models.CharField, models.TextField, models.SlugField)):
        return f"{field_name}__icontains"

    if isinstance(field, models.ForeignKey):
        rel_model = field.remote_field.model
        for attr in (
            "slug",
            "code",
            "name",
            "title",
            "label",
            "descripcion",
            "description",
            "estado",
            "status",
        ):
            try:
                rel_field = rel_model._meta.get_field(attr)
                if isinstance(rel_field, (models.CharField, models.TextField, models.SlugField)):
                    return f"{field_name}__{attr}__icontains"
            except Exception:
                continue

    return None


def _q_status_contains(model_cls, status_field: str | None, keywords: list[str]) -> Q:
    """
    OR con icontains sobre status_field (FK o texto).
    Si no se puede, retorna Q(pk__isnull=True) => 0.
    """
    if not status_field:
        return Q(pk__isnull=True)

    lookup = _build_text_lookup_for_field(model_cls, status_field)
    if not lookup:
        return Q(pk__isnull=True)

    q = Q()
    for kw in keywords:
        q |= Q(**{lookup: kw})
    return q


def _find_date_field_name(model_cls, candidates: list[str]) -> str | None:
    for name in candidates:
        try:
            f = model_cls._meta.get_field(name)
            if isinstance(f, (models.DateField, models.DateTimeField)):
                return name
        except Exception:
            continue
    return None


def _is_datetime_field(model_cls, field_name: str) -> bool:
    try:
        f = model_cls._meta.get_field(field_name)
        return isinstance(f, models.DateTimeField)
    except Exception:
        return False


@login_required
def dashboard(request):
    """
    Dashboard Comercial Pro:
    - KPI Negocios / Cotizaciones
    - Donut Negocios (en proceso vs cerrados)
    - Barras apiladas Cotizaciones por mes (en proceso vs cerradas)
    - Línea Total cotizaciones por mes
    """
    # Ajusta si tus modelos cambian de nombre
    from finanzas_comercial.models import Deal, Quote

    # Detectar campos
    deal_status_field = _find_field_name(Deal, ["status", "estado", "stage", "etapa"])
    quote_status_field = _find_field_name(Quote, ["status", "estado", "stage", "etapa"])

    quote_date_field = _find_date_field_name(
        Quote,
        ["created_at", "created", "fecha", "date", "created_on", "created_date", "updated_at"],
    )

    # Keywords (ES/EN)
    closed_keywords = ["won", "ganad", "lost", "perdid", "cerrad", "closed", "finaliz", "cancel"]
    open_keywords = ["proceso", "progress", "open", "abiert", "en curso", "pend", "draft", "cotiz", "sent"]

    deal_closed_q = _q_status_contains(Deal, deal_status_field, closed_keywords)
    deal_open_q = _q_status_contains(Deal, deal_status_field, open_keywords)

    quote_closed_q = _q_status_contains(Quote, quote_status_field, closed_keywords)
    quote_open_q = _q_status_contains(Quote, quote_status_field, open_keywords)

    # ----- KPIs: Deals -----
    deals_total = Deal.objects.count()
    deals_closed = Deal.objects.filter(deal_closed_q).count()

    # si no puedo detectar open => "en proceso" = no cerrados
    if deal_open_q == Q(pk__isnull=True):
        deals_in_progress = Deal.objects.exclude(deal_closed_q).count()
    else:
        deals_in_progress = Deal.objects.filter(deal_open_q).exclude(deal_closed_q).count()

    # ----- KPIs: Quotes -----
    quotes_total = Quote.objects.count()
    quotes_closed = Quote.objects.filter(quote_closed_q).count()

    if quote_open_q == Q(pk__isnull=True):
        quotes_in_progress = Quote.objects.exclude(quote_closed_q).count()
    else:
        quotes_in_progress = Quote.objects.filter(quote_open_q).exclude(quote_closed_q).count()

    # ----- Serie mensual cotizaciones (últimos 12 meses) -----
    labels: list[str] = []
    in_progress_counts: list[int] = []
    closed_counts: list[int] = []
    total_counts: list[int] = []

    if quote_date_field:
        start_date = (timezone.now() - timedelta(days=365)).date()
        is_dt = _is_datetime_field(Quote, quote_date_field)

        filter_kwargs = {f"{quote_date_field}__date__gte": start_date} if is_dt else {f"{quote_date_field}__gte": start_date}

        qs = (
            Quote.objects.filter(**filter_kwargs)
            .annotate(month=TruncMonth(F(quote_date_field)))
            .values("month")
            .annotate(
                total=Count("id"),
                closed=Count("id", filter=quote_closed_q),
                in_progress=Count("id", filter=Q(~quote_closed_q)),
            )
            .order_by("month")
        )

        for row in qs:
            m = row.get("month")
            if not m:
                continue
            labels.append(m.strftime("%b %Y"))
            total_counts.append(int(row.get("total") or 0))
            in_progress_counts.append(int(row.get("in_progress") or 0))
            closed_counts.append(int(row.get("closed") or 0))

    # JSON para template
    deals_chart = {
        "labels": ["En proceso", "Cerrados"],
        "values": [int(deals_in_progress or 0), int(deals_closed or 0)],
    }

    quotes_chart = {
        "labels": labels,
        "in_progress": in_progress_counts,
        "closed": closed_counts,
        "total": total_counts,
    }

    context = {
        "deals_total": deals_total,
        "deals_in_progress": deals_in_progress,
        "deals_closed": deals_closed,
        "quotes_total": quotes_total,
        "quotes_in_progress": quotes_in_progress,
        "quotes_closed": quotes_closed,
        "deals_chart": deals_chart,
        "quotes_chart": quotes_chart,
    }
    return render(request, "core/dashboard.html", context)
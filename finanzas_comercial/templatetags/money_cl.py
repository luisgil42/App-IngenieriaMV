# finanzas_comercial/templatetags/money_cl.py
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()


def _to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _format_cl_number(n: Decimal, decimals: int) -> str:
    """
    Formato Chile:
      - Miles con punto
      - Decimales con coma (si decimals > 0)
    """
    if decimals < 0:
        decimals = 0

    q = Decimal("1") if decimals == 0 else Decimal("1." + ("0" * decimals))
    n = _to_decimal(n).quantize(q, rounding=ROUND_HALF_UP)

    # separamos signo
    sign = "-" if n < 0 else ""
    n = abs(n)

    # convertimos a string fijo con decimales
    if decimals == 0:
        s = f"{n:.0f}"
        int_part = s
        dec_part = ""
    else:
        s = f"{n:.{decimals}f}"
        int_part, dec_part = s.split(".")

    # miles con punto
    rev = int_part[::-1]
    chunks = [rev[i:i+3] for i in range(0, len(rev), 3)]
    int_fmt = ".".join(ch[::-1] for ch in chunks[::-1])

    if decimals == 0:
        return f"{sign}{int_fmt}"

    # decimales con coma
    return f"{sign}{int_fmt},{dec_part}"


@register.filter(name="money_cl")
def money_cl(value, decimals=0):
    """
    Uso:
      {{ monto|money_cl:0 }}  -> 11.375.000
      {{ monto|money_cl:2 }}  -> 1.234.567,89
    """
    try:
        d = int(decimals)
    except Exception:
        d = 0
    return _format_cl_number(_to_decimal(value), d)
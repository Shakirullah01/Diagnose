from __future__ import annotations

import math

from django import template

register = template.Library()


@register.filter
def floor_months(value):
    """Показывает возраст в месяцах целым вниз: 12.99 -> 12."""
    if value is None or value == "":
        return ""
    try:
        return int(math.floor(float(value)))
    except (TypeError, ValueError):
        return value


from __future__ import annotations

from datetime import date as date_type

from django.utils import timezone


def calculate_age_months_float(birth_date: date_type, *, today: date_type | None = None) -> float:
    """
    Дробный возраст в месяцах (как для `ChildProfile.age_months_float`):
    days / (365.25 / 12), округление до 2 знаков.
    """
    if today is None:
        today = timezone.now().date()
    days = (today - birth_date).days
    if days < 0:
        return 0.0
    return round(days / (365.25 / 12), 2)


def gender_for_display(gender: str | None) -> str:
    if not gender:
        return "—"
    g = str(gender).strip().lower()
    if g in {"male", "m", "м", "мужской", "мужской.", "boy"}:
        return "Мужской"
    if g in {"female", "f", "ж", "женский", "девочка", "girl"}:
        return "Женский"
    # fallback: show original
    return str(gender)


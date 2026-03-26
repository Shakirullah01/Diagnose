from __future__ import annotations

from surveys.constants import STATUS_BORDERLINE, STATUS_NORMAL, STATUS_RISK


def status_from_thresholds(score: float, normal: float, warning: float) -> str:
    """score >= normal → норма; elif score >= warning → пограничное; else → зона риска."""
    if score >= normal:
        return STATUS_NORMAL
    if score >= warning:
        return STATUS_BORDERLINE
    return STATUS_RISK


def final_conclusion_from_statuses(per_category_status: dict[str, str]) -> str:
    """Итоговое текстовое заключение по всем категориям."""
    statuses = [s for s in per_category_status.values() if s]
    if not statuses:
        return "Не удалось сопоставить результаты с нормами. Выполните загрузку данных: python manage.py import_survey_data"
    risk_n = sum(1 for s in statuses if s == STATUS_RISK)
    border_n = sum(1 for s in statuses if s == STATUS_BORDERLINE)
    n = len(statuses)
    if risk_n >= 2 or risk_n > n / 2:
        return "Выраженное отставание развития. Рекомендуется консультация специалиста"
    if risk_n == 0 and border_n == 0:
        return "Развитие соответствует возрастной норме"
    return "Обнаружены отклонения в отдельных областях развития"


def pick_closest_by_age(qs, age_months: float):
    rows = list(qs)
    if not rows:
        return None
    return min(rows, key=lambda r: abs(float(r.age_months) - float(age_months)))

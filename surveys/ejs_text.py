"""ЕЖС: распознавание типов вопросов по тексту (без изменения загрузки из БД)."""

import re


def _normalize_ezhs_question_text(text: str) -> str:
    t = (text or "").strip().lower()
    # Некоторые legacy-вопросы хранятся как "36. Вопрос...".
    return re.sub(r"^\d+\s*[\.\)]\s*", "", t, count=1)


def is_ezhs_satisfaction_question(text: str) -> bool:
    t = _normalize_ezhs_question_text(text)
    return t.startswith("удовлетворены ли вы тем") or t.startswith("насколько вы удовлетворены")


def is_ezhs_legacy_change_question(text: str) -> bool:
    return _normalize_ezhs_question_text(text).startswith("хотите ли вы изменить рутину")

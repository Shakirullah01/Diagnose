from __future__ import annotations

CRITICAL_QUESTION_NUMBERS = {2, 5, 12}

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

RISK_TEXTS = {
    RISK_LOW: "низкий риск",
    RISK_MEDIUM: "средний риск",
    RISK_HIGH: "высокий риск",
}

RISK_RESULT_MESSAGES = {
    RISK_LOW: "Риск расстройства аутистического спектра не выявлен.",
    RISK_MEDIUM: "Обнаружены некоторые признаки риска. Рекомендуется дополнительное наблюдение и консультация специалиста.",
    RISK_HIGH: "Выявлен высокий риск расстройства аутистического спектра. Рекомендуется как можно скорее обратиться к специалисту.",
}


def normalize_yes_no(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in {"да", "yes", "y", "1", "true"}:
        return "yes"
    if raw in {"нет", "no", "n", "0", "false"}:
        return "no"
    return ""


def fail_for_answer(question_order: int, answer_value: str | None) -> bool:
    """
    M-CHAT rules:
    - default: Нет => FAIL, Да => PASS
    - exceptions Q2/Q5/Q12: Да => FAIL, Нет => PASS
    """
    normalized = normalize_yes_no(answer_value)
    if normalized not in {"yes", "no"}:
        return False
    if question_order in CRITICAL_QUESTION_NUMBERS:
        return normalized == "yes"
    return normalized == "no"


def score_for_answer(question_order: int, answer_value: str | None) -> int:
    return 1 if fail_for_answer(question_order, answer_value) else 0


def infer_answer_from_score(question_order: int, score: int | float | None) -> str:
    """
    Restore yes/no for already saved M-CHAT answer score.
    score 1 => FAIL, score 0 => PASS.
    """
    s = int(score or 0)
    if question_order in CRITICAL_QUESTION_NUMBERS:
        return "yes" if s == 1 else "no"
    return "no" if s == 1 else "yes"


def risk_level_from_total(total_score: int | float) -> str:
    score = int(total_score)
    if score <= 2:
        return RISK_LOW
    if score <= 7:
        return RISK_MEDIUM
    return RISK_HIGH


def build_mchat_result(total_score: int | float) -> dict:
    level = risk_level_from_total(total_score)
    return {
        "risk_level": level,
        "risk_level_text": RISK_TEXTS[level],
        "result_text": RISK_RESULT_MESSAGES[level],
    }

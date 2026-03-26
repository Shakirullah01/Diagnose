from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from surveys.constants import STATUS_RISK
from surveys.models import KidNorm
from surveys.scoring_utils import final_conclusion_from_statuses, pick_closest_by_age, status_from_thresholds

if TYPE_CHECKING:
    from surveys.models import Answer, SurveySession


def score_kid_session(session: SurveySession, answers: list[Answer]) -> dict:
    """
    KID: группировка по категории, сумма баллов; F = сумма по всем ответам.
    Норма: ближайший KidNorm по (age_months, category).
    """
    age = session.child_age_months
    if age is None and session.child_profile_id:
        age = session.child_profile.age_months_float()
    if age is None:
        age = 0.0

    sums: dict[str, float] = defaultdict(float)
    total = 0.0
    answered_cats: set[str] = set()
    for ans in answers:
        s = float(ans.score or 0)
        total += s
        cat = (ans.question.category or "").strip().upper()
        if cat:
            sums[cat] += s
            answered_cats.add(cat)

    sums["F"] = total

    per_category_scores: dict[str, float] = {"F": round(total, 2)}
    for k in sorted(sums.keys()):
        if k != "F":
            per_category_scores[k] = round(sums[k], 2)

    per_category_status: dict[str, str] = {}
    per_category_thresholds: dict[str, dict[str, float]] = {}

    cats_for_status = set(answered_cats)
    cats_for_status.add("F")

    for cat in sorted(cats_for_status):
        score = float(sums.get(cat, 0.0))
        norm = pick_closest_by_age(KidNorm.objects.filter(category=cat), age)
        if not norm:
            per_category_status[cat] = ""
            continue
        per_category_thresholds[cat] = {
            "normal": float(norm.normal),
            "warning": float(norm.warning),
            "low": float(norm.low),
        }
        per_category_status[cat] = status_from_thresholds(score, float(norm.normal), float(norm.warning))

    final_conclusion = final_conclusion_from_statuses(per_category_status)

    return {
        "per_category_scores": per_category_scores,
        "per_category_status": per_category_status,
        "per_category_thresholds": per_category_thresholds,
        "final_conclusion": final_conclusion,
        "show_risk_recommendation": STATUS_RISK in per_category_status.values(),
    }

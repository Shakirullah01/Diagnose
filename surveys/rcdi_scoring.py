from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from surveys.constants import RCDI_CATEGORY_CODES, STATUS_RISK
from surveys.models import RCDINorm
from surveys.scoring_utils import final_conclusion_from_statuses, pick_closest_by_age, status_from_thresholds

if TYPE_CHECKING:
    from surveys.models import Answer, SurveySession


def normalize_child_sex(gender: str | None) -> str:
    """M / F для норм RCDI."""
    if not gender:
        return "M"
    g = gender.strip().lower()
    if g in ("м", "m", "male", "мальчик", "boy", "муж", "мужской"):
        return "M"
    if g in ("ж", "f", "female", "девочка", "girl", "жен", "женский"):
        return "F"
    if g.startswith("м") and "ж" not in g[:3]:
        return "M"
    if g.startswith("ж") or "дев" in g:
        return "F"
    return "M"


def score_rcdi_session(session: SurveySession, answers: list[Answer]) -> dict:
    """
    RCDI: возраст + пол + категория; сумма баллов по категориям.
    Норма: ближайший RCDINorm по (age_months, sex, category).
    """
    age = session.child_age_months
    if age is None and session.child_profile_id:
        age = session.child_profile.age_months_float()
    if age is None:
        age = 0.0

    sex = "M"
    if session.child_profile_id:
        sex = normalize_child_sex(session.child_profile.gender)

    sums: dict[str, float] = defaultdict(float)
    for ans in answers:
        s = float(ans.score or 0)
        cat = (ans.question.category or "").strip().upper()
        if cat:
            sums[cat] += s

    per_category_scores = {k: round(sums[k], 2) for k in sorted(sums.keys())}
    per_category_status: dict[str, str] = {}
    per_category_thresholds: dict[str, dict[str, float]] = {}

    for cat in RCDI_CATEGORY_CODES:
        if cat not in sums and not any(
            (a.question.category or "").strip().upper() == cat for a in answers
        ):
            continue
        score = float(sums.get(cat, 0.0))
        norm = pick_closest_by_age(
            RCDINorm.objects.filter(sex=sex, category=cat),
            age,
        )
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
        "rcdi_sex_used": sex,
    }

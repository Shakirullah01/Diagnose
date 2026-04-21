from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import TYPE_CHECKING

from surveys.constants import STATUS_RISK
from surveys.models import KidNorm, Question
from surveys.scoring_utils import final_conclusion_from_statuses, pick_closest_by_age, status_from_thresholds

if TYPE_CHECKING:
    from surveys.models import Answer, SurveySession

_logger = logging.getLogger(__name__)


def _kid_domain_category_by_order(survey_type) -> dict[int, str]:
    """
    KID хранит по два вопроса на один `order`: строка «F» и строка области (COG, MOT, …).
    В интерфейсе показывается один канонический вопрос (обычно с min(id), чаще F),
    ответы привязаны к нему — тогда балл нужно учитывать и в соответствующей области.
    """
    partners: dict[int, str] = {}
    qs = (
        Question.objects.filter(survey_type=survey_type, is_active=True)
        .exclude(category="")
        .exclude(category__iexact="F")
        .order_by("order", "id")
    )
    for q in qs.only("order", "category"):
        o = int(q.order)
        if o in partners:
            continue
        c = (q.category or "").strip().upper()
        if c:
            partners[o] = c
    return partners


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

    st = session.survey_type
    domain_by_order = _kid_domain_category_by_order(st) if st and st.slug == "kdi" else {}

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
        # Ответ сохранён на F-строке, но балл относится и к области развития (вторая строка того же order).
        if st and st.slug == "kdi" and cat == "F":
            dom = domain_by_order.get(int(ans.question.order))
            if dom:
                sums[dom] += s
                answered_cats.add(dom)

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

    if os.getenv("KID_SCORE_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
        norm_cats = sorted(
            {c.upper() for c in KidNorm.objects.values_list("category", flat=True) if c}
        )
        q_cats = sorted({(a.question.category or "").strip().upper() for a in answers if a.question.category})
        _logger.warning(
            "KID_SCORE_DEBUG age=%s norm_categories=%s answer_question_categories=%s "
            "sums=%s per_category_scores=%s answered_cats=%s",
            age,
            norm_cats,
            q_cats,
            {k: round(v, 4) for k, v in sums.items()},
            per_category_scores,
            sorted(answered_cats),
        )

    return {
        "per_category_scores": per_category_scores,
        "per_category_status": per_category_status,
        "per_category_thresholds": per_category_thresholds,
        "final_conclusion": final_conclusion,
        "show_risk_recommendation": STATUS_RISK in per_category_status.values(),
    }

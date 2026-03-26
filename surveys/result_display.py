"""Контекст для страницы результатов (таблица + данные для Chart.js)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from surveys.constants import KID_CATEGORY_LABELS, RCDI_CATEGORY_LABELS, STATUS_BORDERLINE, STATUS_NORMAL, STATUS_RISK
from surveys.kid_scoring import score_kid_session
from surveys.result_messages import get_parent_explanation_block, resolve_parent_result_status
from surveys.rcdi_scoring import score_rcdi_session

if TYPE_CHECKING:
    from surveys.models import SurveySession

KID_ROW_ORDER = ("F", "COG", "MOT", "LAN", "SEL", "SOC")
RCDI_ROW_ORDER = ("SO", "SE", "GR", "FI", "EX", "LA")
KID_RADAR_ORDER = ("COG", "MOT", "LAN", "SEL", "SOC")
RCDI_RADAR_ORDER = ("SO", "SE", "GR", "FI", "EX", "LA")

RADAR_LABELS_KID = {
    "COG": "Когнитивное",
    "MOT": "Движение",
    "LAN": "Речь",
    "SEL": "Самообслуживание",
    "SOC": "Социальное",
}

RADAR_LABELS_RCDI = {
    "SO": "Социальная сфера",
    "SE": "Самообслуживание",
    "GR": "Крупная моторика",
    "FI": "Мелкая моторика",
    "EX": "Экспрессивная речь",
    "LA": "Понимание речи",
}

STATUS_COLORS = {
    STATUS_NORMAL: "#22c55e",
    STATUS_BORDERLINE: "#eab308",
    STATUS_RISK: "#ef4444",
}


def _pack_for_session(session: SurveySession, slug: str) -> dict[str, Any] | None:
    if slug not in ("kdi", "rcdi") or not session.completed_at:
        return None
    answers = list(session.answers.select_related("question"))
    if slug == "kdi":
        return score_kid_session(session, answers)
    return score_rcdi_session(session, answers)


def build_development_result_context(session: SurveySession, slug: str) -> dict[str, Any]:
    """Доп. контекст для шаблона результатов KID/RCDI."""
    pack = _pack_for_session(session, slug)
    if not pack:
        return {
            "development_result": False,
            "result_rows": [],
            "chart_json": "null",
            "radar_chart_json": "null",
            "radar_below_norm_exists": False,
            "show_risk_recommendation": False,
            "rcdi_sex_used": None,
            "parent_result_status": None,
            "parent_explanation_block": None,
        }

    labels = KID_CATEGORY_LABELS if slug == "kdi" else RCDI_CATEGORY_LABELS
    order = KID_ROW_ORDER if slug == "kdi" else RCDI_ROW_ORDER
    scores = pack["per_category_scores"]
    statuses = pack["per_category_status"]
    thresholds = pack["per_category_thresholds"]

    result_rows = []
    chart_labels: list[str] = []
    chart_scores: list[float] = []
    chart_normals: list[float] = []
    bar_colors: list[str] = []

    for code in order:
        if code not in scores:
            continue
        st = statuses.get(code) or ""
        th = thresholds.get(code) or {}
        norm_val = th.get("normal")
        warning_val = th.get("warning")
        label = labels.get(code, code)
        if st == STATUS_NORMAL:
            explanation = "Навыки развиты в пределах возрастной нормы."
        elif st == STATUS_BORDERLINE:
            explanation = "Есть пограничные признаки, стоит наблюдать динамику."
        elif st == STATUS_RISK:
            explanation = "Навыки развиты на уровне ниже возрастной нормы."
        else:
            explanation = "Недостаточно данных для оценки."
        result_rows.append(
            {
                "code": code,
                "label": label,
                "score": scores[code],
                "normal_display": norm_val if norm_val is not None else "—",
                "warning_display": warning_val if warning_val is not None else "—",
                "status": st,
                "status_class": _status_bootstrap_class(st),
                "explanation": explanation,
            }
        )
        chart_labels.append(label)
        chart_scores.append(float(scores[code]))
        chart_normals.append(float(norm_val) if norm_val is not None else 0.0)
        bar_colors.append(STATUS_COLORS.get(st, "#94a3b8"))

    chart_config = {
        "labels": chart_labels,
        "scores": chart_scores,
        "normals": chart_normals,
        "barColors": bar_colors,
    }

    radar_order = KID_RADAR_ORDER if slug == "kdi" else RCDI_RADAR_ORDER
    radar_labels_map = RADAR_LABELS_KID if slug == "kdi" else RADAR_LABELS_RCDI
    radar_labels: list[str] = []
    radar_scores: list[float] = []
    radar_normals: list[float] = []
    below_norm_exists = False
    for code in radar_order:
        if code not in scores:
            continue
        th = thresholds.get(code) or {}
        normal_val = float(th.get("normal") or 0.0)
        score_val = float(scores.get(code) or 0.0)
        radar_labels.append(radar_labels_map.get(code, labels.get(code, code)))
        radar_scores.append(score_val)
        radar_normals.append(normal_val)
        if normal_val > 0 and score_val < normal_val:
            below_norm_exists = True

    radar_chart_config = {
        "labels": radar_labels,
        "scores": radar_scores,
        "normals": radar_normals,
    }

    result_status = resolve_parent_result_status(statuses)

    return {
        "development_result": True,
        "result_rows": result_rows,
        "chart_json": json.dumps(chart_config, ensure_ascii=False),
        "radar_chart_json": json.dumps(radar_chart_config, ensure_ascii=False),
        "radar_below_norm_exists": below_norm_exists,
        "show_risk_recommendation": pack.get("show_risk_recommendation", False),
        "rcdi_sex_used": pack.get("rcdi_sex_used") if slug == "rcdi" else None,
        "final_conclusion_text": pack.get("final_conclusion") or session.result_text,
        "parent_result_status": result_status,
        "parent_explanation_block": get_parent_explanation_block(
            slug,
            result_status,
        ),
    }


def _status_bootstrap_class(status: str) -> str:
    if status == STATUS_NORMAL:
        return "success"
    if status == STATUS_BORDERLINE:
        return "warning"
    if status == STATUS_RISK:
        return "danger"
    return "secondary"

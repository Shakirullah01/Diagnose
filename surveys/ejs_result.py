from collections import defaultdict

from .ejs_text import is_ezhs_legacy_change_question, is_ezhs_satisfaction_question

STATUS_CALM = "calm"
STATUS_MIXED = "mixed"
STATUS_ATTENTION = "attention"

STATUS_TEXT = {
    STATUS_CALM: "Рутина в целом протекает спокойно",
    STATUS_MIXED: "Есть отдельные трудности",
    STATUS_ATTENTION: "Стоит обратить внимание",
}


def _normalized_answer_value(answer) -> str:
    if answer.selected_option and answer.selected_option.value:
        return str(answer.selected_option.value).strip().lower()
    text = (answer.selected_option.text if answer.selected_option else "").strip().lower()
    mapping = {
        "еще не делает": "not_yet",
        "редко": "rare",
        "часто": "often",
        "уже не делает": "not_anymore",
        "да": "yes",
        "нет": "no",
    }
    return mapping.get(text, "")


def _parse_satisfaction_score(answer) -> int | None:
    if answer.selected_option and answer.selected_option.value:
        raw = str(answer.selected_option.value).strip()
        if raw.isdigit():
            value = int(raw)
            if 1 <= value <= 5:
                return value
    text = (answer.selected_option.text if answer.selected_option else "").strip()
    if text.isdigit():
        value = int(text)
        if 1 <= value <= 5:
            return value
    low = text.lower()
    if low == "да":
        return 5
    if low == "нет":
        return 2
    return None


def _status_for_routine(counts: dict) -> str:
    """Статус только по поведенческим ответам. «Уже не делает» — не проблема."""
    n = counts["often"] + counts["rare"] + counts["not_yet"] + counts["not_anymore"]
    if n <= 0:
        return STATUS_MIXED

    often = counts["often"]
    rare = counts["rare"]
    not_yet = counts["not_yet"]
    not_anymore = counts["not_anymore"]
    positive = often + not_anymore

    many_weak = not_yet >= max(2, int(n * 0.35 + 0.5))
    few_weak = not_yet <= int(n * 0.2 + 0.499)
    strong_positive = positive >= max(1, int(n * 0.55 + 0.5))
    calm_skills = strong_positive and few_weak
    very_few_often = often < max(1, int(n * 0.2 + 0.5)) and positive < max(1, int(n * 0.45 + 0.5))

    if many_weak or very_few_often:
        return STATUS_ATTENTION
    if calm_skills:
        return STATUS_CALM
    return STATUS_MIXED


def _discussion_value(raw: str | None) -> bool | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("yes", "да", "1", "true"):
        return True
    if s in ("no", "нет", "0", "false"):
        return False
    return None


def build_ejs_result(
    answers: list,
    routine_question_counts: dict | None = None,
    parent_discussion_requests: dict | None = None,
) -> dict:
    grouped = defaultdict(list)
    for ans in answers:
        routine = (ans.question.category or "").strip() or "Без категории"
        grouped[routine].append(ans)

    routine_names = sorted(set(grouped.keys()))
    if routine_question_counts:
        ordered_from_map = [k for k in routine_question_counts.keys()]
        missing = [k for k in routine_names if k not in routine_question_counts]
        routine_names = ordered_from_map + sorted(missing)

    discussion_by_name: dict[str, bool | None] = {}
    if parent_discussion_requests:
        for k, v in parent_discussion_requests.items():
            if isinstance(v, bool):
                discussion_by_name[str(k)] = v
            elif v is None:
                discussion_by_name[str(k)] = None
            else:
                discussion_by_name[str(k)] = _discussion_value(str(v))

    routines = []
    for routine_name in routine_names:
        eligible_questions_count = None
        if routine_question_counts is not None:
            eligible_questions_count = int(routine_question_counts.get(routine_name, 0))
        if eligible_questions_count == 0:
            routines.append(
                {
                    "name": routine_name,
                    "is_empty": True,
                    "empty_text": "Для данной возрастной категории вопросы по этой рутине отсутствуют",
                    "counts": {"often": 0, "rare": 0, "not_yet": 0, "not_anymore": 0},
                    "satisfaction_score": None,
                    "parent_wants_discussion": None,
                    "status_code": None,
                    "status_text": "",
                    "questions": [],
                }
            )
            continue

        items = sorted(grouped[routine_name], key=lambda a: (a.question.order, a.question_id))
        counts = {"often": 0, "rare": 0, "not_yet": 0, "not_anymore": 0}
        satisfaction_score = None
        question_rows = []

        for ans in items:
            q_text = ans.question.text
            if is_ezhs_legacy_change_question(q_text):
                continue
            value = _normalized_answer_value(ans)

            if is_ezhs_satisfaction_question(q_text):
                parsed_sat = _parse_satisfaction_score(ans)
                if parsed_sat is not None:
                    satisfaction_score = parsed_sat
            elif value in counts:
                counts[value] += 1

            question_rows.append(
                {
                    "order": ans.question.order,
                    "text": q_text,
                    "age_label": (
                        f"от {ans.question.age_min_months} мес."
                        if ans.question.age_min_months is not None
                        else "—"
                    ),
                    "answer_text": ans.selected_option.text if ans.selected_option else "—",
                }
            )

        status_code = _status_for_routine(counts)
        parent_wants = discussion_by_name.get(routine_name)
        routines.append(
            {
                "name": routine_name,
                "is_empty": False,
                "counts": counts,
                "satisfaction_score": satisfaction_score,
                "parent_wants_discussion": parent_wants,
                "status_code": status_code,
                "status_text": STATUS_TEXT[status_code],
                "questions": question_rows,
            }
        )

    problematic = [
        r
        for r in routines
        if (not r.get("is_empty")) and r["status_code"] in {STATUS_ATTENTION, STATUS_MIXED}
    ]
    problematic_count = len(problematic)
    if problematic_count >= 2:
        final_recommendation = "Есть несколько рутин, где стоит обсудить ситуацию со специалистом"
    else:
        final_recommendation = "В целом развитие повседневных навыков соответствует возрасту"

    discussion_yes = [r["name"] for r in routines if r.get("parent_wants_discussion") is True]

    key_signals = {
        "problematic_routines": [r["name"] for r in problematic],
        "parent_requests_discussion": discussion_yes,
    }

    return {
        "routines": routines,
        "problematic_routines_count": problematic_count,
        "final_recommendation": final_recommendation,
        "key_signals": key_signals,
        "parent_discussion_requests": {r["name"]: r.get("parent_wants_discussion") for r in routines if not r.get("is_empty")},
    }

from math import ceil

from django.db import connection
from django.db.models import Prefetch
from django.shortcuts import render

from .models import AnswerOption, Question, SurveyType


SURVEY_LABELS: dict[str, str] = {
    "kdi": "КИД",
    "rcdi": "RCDI",
    "ezhs": "ЕЖС",
    "m-chat": "M-CHAT",
}


def home(request):
    return render(request, "home.html")


def _ensure_questions_imported_from_legacy(slug: str) -> SurveyType | None:
    """
    Для КИД, RCDI, ЕЖС и M-CHAT один раз импортируем вопросы
    из существующих таблиц (kdi_questions, rcdi_questions, ejs_questions, m_chat_questions)
    в модель Question.
    """
    if slug not in {"kdi", "rcdi", "ezhs", "m-chat"}:
        return SurveyType.objects.filter(slug=slug).first()

    survey_type, _ = SurveyType.objects.get_or_create(
        slug=slug,
        defaults={"name": SURVEY_LABELS.get(slug, slug.upper())},
    )

    # Если вопросы уже загружены в нашу модель, ничего не делаем
    if Question.objects.filter(survey_type=survey_type).exists():
        return survey_type

    with connection.cursor() as cursor:
        try:
            if slug == "kdi":
                cursor.execute(
                    "SELECT question_order, question FROM kdi_questions ORDER BY question_order"
                )
                rows = cursor.fetchall()
                bulk = [
                    Question(
                        survey_type=survey_type,
                        text=text,
                        order=order or 0,
                        is_active=True,
                    )
                    for (order, text) in rows
                ]
            elif slug == "rcdi":
                cursor.execute(
                    "SELECT question_order, Question FROM rcdi_questions ORDER BY question_order"
                )
                rows = cursor.fetchall()
                bulk = [
                    Question(
                        survey_type=survey_type,
                        text=text,
                        order=order or 0,
                        is_active=True,
                    )
                    for (order, text) in rows
                ]
            elif slug == "ezhs":
                # ЕЖС: есть возрастной диапазон в текстовом поле age, например '5-24' или '0-36'
                cursor.execute(
                    "SELECT question_order, question, age FROM ejs_questions ORDER BY question_order"
                )
                rows = cursor.fetchall()
                bulk = []
                for order, text, age_str in rows:
                    age_min = None
                    age_max = None
                    if age_str:
                        part = str(age_str).strip()
                        if "-" in part:
                            a, b = part.split("-", 1)
                            try:
                                age_min = int(a)
                            except ValueError:
                                age_min = 0
                            try:
                                age_max = int(b)
                            except ValueError:
                                age_max = 36
                        else:
                            try:
                                single = int(part)
                            except ValueError:
                                single = 0
                            age_min = single
                            age_max = single
                    bulk.append(
                        Question(
                            survey_type=survey_type,
                            text=text,
                            order=order or 0,
                            is_active=True,
                            age_min_months=age_min,
                            age_max_months=age_max,
                        )
                    )
            else:  # m-chat
                cursor.execute(
                    "SELECT question_order, question FROM m_chat_questions ORDER BY question_order"
                )
                rows = cursor.fetchall()
                bulk = [
                    Question(
                        survey_type=survey_type,
                        text=text,
                        order=order or 0,
                        is_active=True,
                    )
                    for (order, text) in rows
                ]
        except Exception:
            return survey_type

    if bulk:
        Question.objects.bulk_create(bulk)

    return survey_type


def survey_page(request, slug: str):
    title = SURVEY_LABELS.get(slug, slug.upper())

    # Для опросников подтягиваем вопросы из существующих таблиц,
    # затем работаем через обычные Django-модели.
    survey_type = _ensure_questions_imported_from_legacy(slug)

    age_months: int | None = None
    age_error: str | None = None

    if slug == "ezhs":
        age_param = (request.GET.get("age") or "").strip()
        if age_param:
            try:
                age_val = int(age_param)
                if age_val < 0 or age_val > 36:
                    age_error = "Возраст должен быть от 0 до 36 месяцев."
                else:
                    age_months = age_val
            except ValueError:
                age_error = "Введите целое число месяцев."

    base_qs = Question.objects.filter(survey_type=survey_type, is_active=True) if survey_type else Question.objects.none()

    if slug == "ezhs":
        # Пока не введён корректный возраст — вопросы не показываем
        if age_months is None or age_error:
            base_qs = Question.objects.none()
        else:
            base_qs = base_qs.filter(
                age_min_months__lte=age_months,
                age_max_months__gte=age_months,
            )

    # Пагинация: максимум 20 вопросов на страницу
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    per_page = 20
    total = base_qs.count()
    total_pages = max(1, ceil(total / per_page)) if total else 1
    page = min(max(page, 1), total_pages)

    start = (page - 1) * per_page
    end = start + per_page

    questions = (
        base_qs.order_by("order", "id")
        .prefetch_related(Prefetch("answer_options", queryset=AnswerOption.objects.all()))[start:end]
    )

    shown_until = min(end, total) if total else 0
    progress_percent = int((shown_until / total) * 100) if total else 0
    first_index = start + 1 if total else 0
    last_index = shown_until

    context = {
        "survey_slug": slug,
        "survey_title": title,
        "survey_type": survey_type,
        "questions": questions,
        "progress_percent": progress_percent,
        "page": page,
        "total_pages": total_pages,
        "total_questions": total,
        "first_index": first_index,
        "last_index": last_index,
        "age_months": age_months,
        "age_error": age_error,
    }
    return render(request, "surveys/survey_page.html", context)


from math import ceil

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connection
from django.db.models import Prefetch, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from django.utils import timezone

from children.models import ChildProfile
from .models import Answer, AnswerOption, KidNorms, Question, SpecialistNote, SurveySession, SurveyScaleOption, SurveyType


SURVEY_LABELS: dict[str, str] = {
    "kdi": "КИД",
    "rcdi": "RCDI",
    "ezhs": "ЕЖС",
    "m-chat": "M-CHAT",
}

# Instruction page content (Russian). Keys: title, body (list of paragraphs/bullets), ask_age (min, max) or None
SURVEY_INSTRUCTIONS: dict[str, dict] = {
    "kdi": {
        "title": "Оценка развития детей до 16 месяцев по шкале KID",
        "body": [
            "Шкала KID предназначена для оценки уровня развития младенцев в возрасте от 2 до 16 месяцев.",
            "Опрос должен заполнять человек, который ежедневно проводит с ребёнком большую часть времени (обычно мать, отец, бабушка или няня). Специальных знаний не требуется — достаточно внимательно прочитать вопросы и честно ответить на них.",
            "При заполнении опроса: внимательно прочитайте каждый пункт; выберите один вариант ответа; не оставляйте вопросы без ответа.",
            "Правила выбора ответа: 1 — ребёнок начал выполнять это действие в течение последнего месяца; 2 — ребёнок выполняет это действие уже давно (более месяца); 3 — ребёнок пока не выполняет это действие. Даже если многие действия пока слишком сложные для ребёнка, необходимо выбрать вариант 3.",
            "После завершения опроса система автоматически рассчитает результаты и покажет уровень развития ребёнка.",
        ],
        "ask_age": (2, 16),
    },
    "rcdi": {
        "title": "Шкала развития детей RCDI (14 месяцев – 3,5 лет)",
        "body": [
            "Данный опрос предназначен для оценки развития детей в возрасте от 14 месяцев до 3,5 лет.",
            "Перед началом внимательно проверьте дату рождения ребёнка и дату прохождения теста.",
            "Отвечая на вопросы, выбирайте один из вариантов: 1 — ребёнок начал выполнять действие в течение последнего месяца; 2 — ребёнок выполняет это действие уже давно; 3 — ребёнок пока не выполняет это действие. Не оставляйте вопросы без ответа и не выбирайте несколько вариантов одновременно.",
            "После завершения опроса система автоматически сформирует результат оценки развития.",
        ],
        "ask_age": (14, 42),
    },
    "m-chat": {
        "title": "Скрининговый тест M-CHAT для выявления признаков аутизма",
        "body": [
            "M-CHAT — это скрининговый опросник для выявления риска расстройств аутистического спектра у детей в возрасте от 16 до 30 месяцев. Опрос состоит из 23 вопросов о поведении ребёнка.",
            "Важно понимать: данный тест не ставит диагноз; он лишь определяет риск наличия признаков аутизма. Если по результатам теста будет выявлен повышенный риск, рекомендуется обратиться к специалисту.",
            "Пожалуйста, внимательно ответьте на каждый вопрос, исходя из обычного поведения ребёнка.",
        ],
        "ask_age": (16, 30),
    },
    "ezhs": {
        "title": "Опросник ЕЖС (ежедневные жизненные ситуации)",
        "body": [
            "Данный опросник касается повседневных ситуаций и поведения ребёнка. Укажите возраст ребёнка в месяцах на следующем шаге — будут показаны только подходящие по возрасту вопросы.",
            "Отвечайте честно и не пропускайте вопросы.",
        ],
        "ask_age": None,
    },
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


def _compute_kid_result(session: SurveySession) -> str:
    """KID only: compare total_score to KidNorms; return one of two result texts."""
    if session.final_score is None or session.child_age_months is None:
        return ""
    norms = KidNorms.objects.filter(age_months=session.child_age_months).first()
    if not norms:
        norms = KidNorms.objects.order_by("age_months").first()
        for n in KidNorms.objects.order_by("age_months"):
            if n.age_months <= session.child_age_months:
                norms = n
        if not norms:
            return ""
    score = session.final_score
    if score >= norms.normal_score:
        return "Развитие соответствует возрастной норме"
    return "Наблюдаются признаки возможного отставания развития"


def survey_start(request, slug: str):
    """Show instruction page; on POST create session and redirect to survey."""
    if slug not in SURVEY_INSTRUCTIONS:
        return redirect("survey_page", slug=slug)
    survey_type = _ensure_questions_imported_from_legacy(slug)
    if not survey_type:
        return redirect("home")

    # For KID, RCDI, M-CHAT: logged-in parents must select a child profile (from dashboard)
    child_profile = None
    if request.user.is_authenticated and slug in ("kdi", "rcdi", "m-chat"):
        profile_id = request.GET.get("child_profile")
        if not profile_id:
            return redirect("parent_dashboard")
        try:
            child_profile = get_object_or_404(ChildProfile, pk=int(profile_id), parent=request.user)
        except (ValueError, TypeError):
            return redirect("parent_dashboard")

    title = SURVEY_LABELS.get(slug, slug.upper())
    instruction = SURVEY_INSTRUCTIONS[slug]
    ask_age = instruction.get("ask_age")
    age_error = None

    if request.method == "POST":
        child_age_months = None
        if child_profile:
            child_age_months = child_profile.age_months()
        if ask_age and not child_age_months:
            try:
                raw = request.POST.get("child_age_months", "").strip()
                child_age_months = int(raw)
                low, high = ask_age
                if child_age_months < low or child_age_months > high:
                    age_error = f"Укажите возраст от {low} до {high} месяцев."
            except (ValueError, TypeError):
                age_error = "Введите целое число (возраст в месяцах)."
        if age_error:
            pass
        else:
            if slug == "ezhs":
                return redirect("survey_page", slug=slug)
            session = SurveySession.objects.create(
                user=request.user if request.user.is_authenticated else None,
                child_profile=child_profile,
                survey_type=survey_type,
                child_age_months=child_age_months or (child_profile.age_months() if child_profile else None),
            )
            url = reverse("survey_page", args=[slug]) + "?session_id=" + str(session.pk)
            return redirect(url)

    context = {
        "survey_slug": slug,
        "survey_title": title,
        "instruction_title": instruction["title"],
        "instruction_body": instruction["body"],
        "ask_age": ask_age,
        "age_error": age_error,
        "child_profile": child_profile,
    }
    return render(request, "surveys/survey_start.html", context)


def survey_page(request, slug: str):
    title = SURVEY_LABELS.get(slug, slug.upper())
    session_id_raw = request.GET.get("session_id")
    survey_session = None
    if session_id_raw:
        try:
            sid = int(session_id_raw)
            survey_session = SurveySession.objects.filter(
                pk=sid, survey_type__slug=slug, completed_at__isnull=True
            ).select_related("survey_type").first()
        except ValueError:
            pass

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
        page = int(request.GET.get("page", request.POST.get("page", "1")))
    except (ValueError, TypeError):
        page = 1
    per_page = 20
    total = base_qs.count()
    total_pages = max(1, ceil(total / per_page)) if total else 1
    page = min(max(page, 1), total_pages)

    start = (page - 1) * per_page
    end = start + per_page

    # Scale options for KID/RCDI (1,2,3 with scores)
    scale_options = []
    if survey_type and slug in ("kdi", "rcdi"):
        scale_options = list(SurveyScaleOption.objects.filter(survey_type=survey_type).order_by("value"))

    questions = (
        base_qs.order_by("order", "id")
        .prefetch_related(Prefetch("answer_options", queryset=AnswerOption.objects.all()))[start:end]
    )

    # POST: save answers for this page; then redirect to next page or result
    if request.method == "POST" and survey_session and survey_type:
        scale_option_ids = {o.pk: o for o in SurveyScaleOption.objects.filter(survey_type=survey_type)}
        for q in questions:
            key = f"q_{q.id}"
            opt_id = request.POST.get(key)
            if not opt_id:
                continue
            try:
                opt_id = int(opt_id)
            except (ValueError, TypeError):
                continue
            scale_opt = scale_option_ids.get(opt_id)
            if not scale_opt:
                continue
            ans, _ = Answer.objects.update_or_create(
                session=survey_session,
                question=q,
                defaults={
                    "selected_scale_option": scale_opt,
                    "score": scale_opt.score,
                },
            )
        if page < total_pages:
            url = reverse("survey_page", args=[slug]) + f"?session_id={survey_session.pk}&page={page + 1}"
            return redirect(url)
        # Last page: compute total and result
        total_score = Answer.objects.filter(session=survey_session).aggregate(s=Sum("score"))["s"] or 0
        survey_session.final_score = total_score if slug == "kdi" else None
        survey_session.completed_at = timezone.now()
        if slug == "kdi":
            survey_session.result_text = _compute_kid_result(survey_session)
        elif slug in ("rcdi", "m-chat"):
            survey_session.result_text = "Опрос завершен. Результаты будут обработаны специалистом."
        else:
            survey_session.result_text = "Опрос завершён."
        survey_session.save(update_fields=["final_score", "completed_at", "result_text"])
        return redirect("survey_result", slug=slug, session_id=survey_session.pk)

    shown_until = min(end, total) if total else 0
    progress_percent = int((shown_until / total) * 100) if total else 0
    first_index = start + 1 if total else 0
    last_index = shown_until

    context = {
        "survey_slug": slug,
        "survey_title": title,
        "survey_type": survey_type,
        "survey_session": survey_session,
        "questions": questions,
        "scale_options": scale_options,
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


def survey_result(request, slug: str, session_id: int):
    """Show result after survey completion; allow consent to send to specialist."""
    session = get_object_or_404(
        SurveySession.objects.select_related("survey_type", "child_profile", "child", "user"),
        pk=session_id,
        survey_type__slug=slug,
        completed_at__isnull=False,
    )
    if request.method == "POST" and request.POST.get("consent") == "1":
        session.consent_to_send = True
        session.save(update_fields=["consent_to_send"])
        return redirect("survey_result", slug=slug, session_id=session_id)

    context = {
        "survey_slug": slug,
        "survey_title": SURVEY_LABELS.get(slug, slug.upper()),
        "session": session,
    }
    return render(request, "surveys/survey_result.html", context)


def _specialist_required(user) -> bool:
    return user.is_authenticated and getattr(user, "is_specialist", False)


@login_required
@user_passes_test(_specialist_required)
def specialist_dashboard(request):
    sessions = (
        SurveySession.objects.select_related("child_profile", "child", "user", "survey_type")
        .filter(consent_to_send=True)
        .order_by("-started_at")
    )

    total_cases = sessions.count()
    new_cases = sessions.filter(status=SurveySession.STATUS_NEW).count()
    pending_cases = sessions.filter(status=SurveySession.STATUS_NEW).count()

    context = {
        "sessions": sessions,
        "total_cases": total_cases,
        "new_cases": new_cases,
        "pending_cases": pending_cases,
    }
    return render(request, "specialist/dashboard.html", context)


@login_required
@user_passes_test(_specialist_required)
def specialist_case_detail(request, pk: int):
    session = get_object_or_404(
        SurveySession.objects.select_related("child_profile", "child", "user", "survey_type").prefetch_related(
            Prefetch(
                "answers",
                queryset=Answer.objects.select_related("question", "selected_option", "selected_scale_option").order_by("question__order"),
            ),
            "notes",
        ),
        pk=pk,
        consent_to_send=True,
    )

    if request.method == "POST":
        comment = request.POST.get("comment", "").strip()
        recommendation = request.POST.get("recommendation", "").strip()
        action = request.POST.get("action")

        if comment or recommendation:
            SpecialistNote.objects.create(
                survey_session=session,
                specialist=request.user,
                comment=comment,
                recommendation=recommendation,
            )

        if action == "mark_viewed":
            session.status = SurveySession.STATUS_VIEWED
            session.save(update_fields=["status"])

        return redirect("specialist_case_detail", pk=session.pk)

    context = {
        "session": session,
    }
    return render(request, "specialist/case_detail.html", context)


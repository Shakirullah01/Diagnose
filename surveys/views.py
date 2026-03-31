from math import ceil
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connection
from django.db.models import Prefetch, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from django.utils import timezone

from children.models import ChildProfile
from .kid_scoring import score_kid_session
from .mchat_scoring import RISK_TEXTS, build_mchat_result, infer_answer_from_score, score_for_answer
from .models import Answer, AnswerOption, Question, SpecialistNote, SurveySession, SurveyScaleOption, SurveyType
from .rcdi_scoring import score_rcdi_session
from .result_display import build_development_result_context


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


def _is_specialist(user) -> bool:
    return user.is_authenticated and getattr(user, "is_specialist", False)


def _is_parent(user) -> bool:
    return user.is_authenticated and getattr(user, "role", "") == "parent"


def _survey_age_allowed(slug: str, age_months: float | None) -> tuple[bool, str]:
    if age_months is None:
        return False, "Не удалось определить возраст ребёнка."
    age = float(age_months)
    if slug == "kdi" and not (2 <= age <= 16):
        return False, "Опрос KID доступен для возраста от 2 до 16 месяцев."
    if slug == "rcdi" and not (14 <= age <= 42):
        return False, "Опрос RCDI доступен для возраста от 14 до 42 месяцев."
    if slug == "m-chat" and not (16 <= age <= 30):
        return False, "Опрос M-CHAT доступен для возраста от 16 до 30 месяцев."
    return True, ""


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


def survey_start(request, slug: str):
    """Show instruction page; on POST create session and redirect to survey."""
    if _is_specialist(request.user):
        return redirect("specialist_dashboard")
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
            age_val = child_profile.age_months_float()
            ok, err_msg = _survey_age_allowed(slug, age_val)
            if not ok:
                messages.error(request, err_msg)
                return redirect("parent_dashboard")
        except (ValueError, TypeError):
            return redirect("parent_dashboard")

    title = SURVEY_LABELS.get(slug, slug.upper())
    instruction = SURVEY_INSTRUCTIONS[slug]
    ask_age = instruction.get("ask_age")
    age_error = None

    if request.method == "POST":
        child_age_months = None
        if child_profile:
            child_age_months = child_profile.age_months_float()
        if ask_age and child_age_months is None:
            try:
                raw = request.POST.get("child_age_months", "").strip()
                child_age_months = float(int(raw))
                low, high = ask_age
                if int(child_age_months) < low or int(child_age_months) > high:
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
                child_age_months=child_age_months
                if child_age_months is not None
                else (child_profile.age_months_float() if child_profile else None),
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
    if _is_specialist(request.user):
        return redirect("specialist_dashboard")
    title = SURVEY_LABELS.get(slug, slug.upper())
    session_id_raw = request.GET.get("session_id")
    survey_session = None
    if session_id_raw:
        try:
            sid = int(session_id_raw)
            survey_session = SurveySession.objects.filter(
                pk=sid, survey_type__slug=slug, completed_at__isnull=True
            ).select_related("survey_type").first()
            if survey_session and survey_session.child_profile_id:
                ok, err_msg = _survey_age_allowed(slug, survey_session.child_age_months)
                if not ok:
                    messages.error(request, err_msg)
                    return redirect("parent_dashboard")
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
    if survey_type and slug in ("kdi", "rcdi"):
        base_qs = base_qs.exclude(category="")

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
    existing_answers = {}
    if survey_session:
        for ans in Answer.objects.filter(session=survey_session, question__in=questions).select_related("question"):
            if slug == "m-chat":
                existing_answers[ans.question_id] = infer_answer_from_score(ans.question.order, ans.score)
            elif ans.selected_scale_option_id:
                existing_answers[ans.question_id] = str(ans.selected_scale_option_id)
            elif ans.selected_option_id:
                existing_answers[ans.question_id] = str(ans.selected_option_id)

    # POST: save answers for this page; then redirect to next page or result
    if request.method == "POST" and survey_session and survey_type:
        scale_option_ids = {o.pk: o for o in SurveyScaleOption.objects.filter(survey_type=survey_type)}
        missing_questions = []
        for q in questions:
            key = f"q_{q.id}"
            if slug == "m-chat":
                answer_value = request.POST.get(key)
                if not answer_value:
                    missing_questions.append(q.order)
                    continue
                score = score_for_answer(q.order, answer_value)
                Answer.objects.update_or_create(
                    session=survey_session,
                    question=q,
                    defaults={
                        "selected_option": None,
                        "selected_scale_option": None,
                        "score": float(score),
                    },
                )
            else:
                opt_id = request.POST.get(key)
                if not opt_id:
                    missing_questions.append(q.order)
                    continue
                try:
                    opt_id = int(opt_id)
                except (ValueError, TypeError):
                    continue
                scale_opt = scale_option_ids.get(opt_id)
                if not scale_opt:
                    continue
                Answer.objects.update_or_create(
                    session=survey_session,
                    question=q,
                    defaults={
                        "selected_scale_option": scale_opt,
                        "score": scale_opt.score,
                    },
                )
        if missing_questions:
            messages.error(request, "Ответьте на все вопросы на странице перед продолжением.")
            return redirect(reverse("survey_page", args=[slug]) + f"?session_id={survey_session.pk}&page={page}")
        if page < total_pages:
            url = reverse("survey_page", args=[slug]) + f"?session_id={survey_session.pk}&page={page + 1}"
            return redirect(url)
        # Last page: compute total and result
        total_score = Answer.objects.filter(session=survey_session).aggregate(s=Sum("score"))["s"] or 0
        answered_total = Answer.objects.filter(session=survey_session).count()
        if answered_total <= 0:
            messages.error(request, "Нельзя завершить пустую анкету.")
            return redirect(reverse("survey_page", args=[slug]) + f"?session_id={survey_session.pk}&page={page}")
        if answered_total < total:
            messages.error(request, "Анкета заполнена не полностью. Проверьте, что все вопросы отвечены.")
            return redirect(reverse("survey_page", args=[slug]) + f"?session_id={survey_session.pk}&page=1")
        survey_session.completed_at = timezone.now()
        answers_for_score = list(
            Answer.objects.filter(session=survey_session).select_related("question")
        )
        if slug == "kdi":
            survey_session.total_score = float(total_score)
            survey_session.risk_level = None
            pack = score_kid_session(survey_session, answers_for_score)
            survey_session.per_category_scores = pack["per_category_scores"]
            survey_session.per_category_status = pack["per_category_status"]
            survey_session.result_text = pack["final_conclusion"]
        elif slug == "rcdi":
            survey_session.total_score = float(total_score)
            survey_session.risk_level = None
            pack = score_rcdi_session(survey_session, answers_for_score)
            survey_session.per_category_scores = pack["per_category_scores"]
            survey_session.per_category_status = pack["per_category_status"]
            survey_session.result_text = pack["final_conclusion"]
        elif slug == "m-chat":
            survey_session.total_score = float(total_score)
            survey_session.per_category_scores = {"failed_questions": int(total_score)}
            survey_session.per_category_status = None
            mchat_result = build_mchat_result(total_score)
            survey_session.risk_level = mchat_result["risk_level"]
            survey_session.result_text = mchat_result["result_text"]
        else:
            survey_session.total_score = float(total_score) if slug in ("ezhs", "m-chat") else None
            survey_session.risk_level = None
            survey_session.per_category_scores = None
            survey_session.per_category_status = None
            if slug == "m-chat":
                survey_session.result_text = "Опрос завершен. Результаты будут обработаны специалистом."
            else:
                survey_session.result_text = "Опрос завершён."
        survey_session.save(
            update_fields=["completed_at", "result_text", "total_score", "risk_level", "per_category_scores", "per_category_status"]
        )
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
        "existing_answers": existing_answers,
        "existing_answers_json": json.dumps(existing_answers),
    }
    return render(request, "surveys/survey_page.html", context)


def survey_result(request, slug: str, session_id: int):
    """Show result after survey completion; allow consent to send to specialist."""
    if _is_specialist(request.user):
        return redirect("specialist_dashboard")
    session = get_object_or_404(
        SurveySession.objects.select_related("survey_type", "child_profile", "child", "user"),
        pk=session_id,
        survey_type__slug=slug,
        completed_at__isnull=False,
    )
    if request.user.is_authenticated and not _is_specialist(request.user):
        owner_ok = False
        if session.user_id and session.user_id == request.user.id:
            owner_ok = True
        if session.child_profile_id and session.child_profile and session.child_profile.parent_id == request.user.id:
            owner_ok = True
        if not owner_ok:
            return HttpResponseForbidden("Доступ запрещён.")
    if request.method == "POST" and request.POST.get("consent") == "1":
        session.consent_to_send = True
        session.save(update_fields=["consent_to_send"])
        return redirect("survey_result", slug=slug, session_id=session_id)

    context = {
        "survey_slug": slug,
        "survey_title": SURVEY_LABELS.get(slug, slug.upper()),
        "session": session,
    }
    context.update(build_development_result_context(session, slug))
    if slug == "m-chat":
        failed_questions = int(session.total_score or 0)
        risk_level_text = RISK_TEXTS.get(session.risk_level or "", "")
        failed_answers = []
        for ans in session.answers.select_related("question").order_by("question__order"):
            if int(ans.score or 0) == 1:
                failed_answers.append(
                    {
                        "order": ans.question.order,
                        "text": ans.question.text,
                    }
                )
        context.update(
            {
                "mchat_failed_questions": failed_questions,
                "mchat_risk_level_text": risk_level_text,
                "mchat_failed_answers": failed_answers,
            }
        )
    if session.notes.exists():
        latest_note = session.notes.first()
    else:
        latest_note = None
    context["latest_specialist_note"] = latest_note
    return render(request, "surveys/survey_result.html", context)


def _specialist_required(user) -> bool:
    return _is_specialist(user)


@login_required
@user_passes_test(_specialist_required)
def specialist_dashboard(request):
    sessions_qs = (
        SurveySession.objects.select_related("child_profile", "child", "user", "survey_type")
        .filter(consent_to_send=True)
        .order_by("-started_at")
    )
    survey_filter = (request.GET.get("survey") or "").strip()
    risk_filter = (request.GET.get("risk") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    age_min = (request.GET.get("age_min") or "").strip()
    age_max = (request.GET.get("age_max") or "").strip()

    if survey_filter:
        sessions_qs = sessions_qs.filter(survey_type__slug=survey_filter)
    if status_filter:
        sessions_qs = sessions_qs.filter(status=status_filter)
    if age_min.isdigit():
        sessions_qs = sessions_qs.filter(child_age_months__gte=float(age_min))
    if age_max.isdigit():
        sessions_qs = sessions_qs.filter(child_age_months__lte=float(age_max))

    sessions = list(sessions_qs)
    if risk_filter == "risk":
        sessions = [
            s for s in sessions
            if (s.survey_type.slug == "m-chat" and s.risk_level == "high")
            or ("зона риска" in (s.per_category_status or {}).values())
        ]
    elif risk_filter == "borderline":
        sessions = [
            s for s in sessions
            if (s.survey_type.slug == "m-chat" and s.risk_level == "medium")
            or ("пограничное состояние" in (s.per_category_status or {}).values())
        ]
    elif risk_filter == "normal":
        sessions = [
            s for s in sessions
            if (s.survey_type.slug == "m-chat" and s.risk_level == "low")
            or (s.per_category_status and all(v == "норма" for v in (s.per_category_status or {}).values()))
        ]

    for s in sessions:
        if s.survey_type.slug == "m-chat" and s.risk_level:
            s.risk_level = s.risk_level
            continue
        statuses = list((s.per_category_status or {}).values())
        if "зона риска" in statuses:
            s.risk_level = "risk"
        elif "пограничное состояние" in statuses:
            s.risk_level = "borderline"
        elif statuses:
            s.risk_level = "normal"
        else:
            s.risk_level = "unknown"

    total_cases = len(sessions)
    new_cases = sum(1 for s in sessions if s.status == SurveySession.STATUS_NEW)
    pending_cases = new_cases

    context = {
        "sessions": sessions,
        "total_cases": total_cases,
        "new_cases": new_cases,
        "pending_cases": pending_cases,
        "selected_survey": survey_filter,
        "selected_risk": risk_filter,
        "selected_status": status_filter,
        "selected_age_min": age_min,
        "selected_age_max": age_max,
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

    detail_rows = []
    mchat_failed_answers = []
    answer_rows = []
    for ans in session.answers.all():
        answer_text = "не выбран"
        if ans.selected_scale_option:
            answer_text = f"{ans.selected_scale_option.value} — {ans.selected_scale_option.text}"
        elif ans.selected_option:
            answer_text = ans.selected_option.text
        elif session.survey_type.slug == "m-chat":
            answer_text = "Да" if infer_answer_from_score(ans.question.order, ans.score) == "yes" else "Нет"
        answer_rows.append({"answer": ans, "answer_text": answer_text})
    if session.survey_type.slug in ("kdi", "rcdi"):
        pack = build_development_result_context(session, session.survey_type.slug)
        for row in pack.get("result_rows", []):
            detail_rows.append(
                {
                    "label": row["label"],
                    "score": row["score"],
                    "normal": row.get("normal_display", "—"),
                    "warning": row.get("warning_display", "—"),
                    "status": row.get("status", ""),
                }
            )
    elif session.survey_type.slug == "m-chat":
        for ans in session.answers.select_related("question").order_by("question__order"):
            if int(ans.score or 0) == 1:
                mchat_failed_answers.append(ans)

    context = {
        "session": session,
        "detail_rows": detail_rows,
        "mchat_failed_answers": mchat_failed_answers,
        "answer_rows": answer_rows,
    }
    return render(request, "specialist/case_detail.html", context)


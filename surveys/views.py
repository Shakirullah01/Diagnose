from math import ceil
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connection
from django.db.models import Min, Prefetch, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from django.utils import timezone

from children.models import ChildProfile
from children.forms import ChildProfileForm
from .kid_scoring import score_kid_session
from .mchat_scoring import RISK_TEXTS, build_mchat_result, infer_answer_from_score, score_for_answer
from .forms import GuestContactForm, GuestSurveyStartForm
from .age_utils import calculate_age_months_float, gender_for_display
from .models import Answer, AnswerOption, Question, SpecialistNote, SurveySession, SurveyScaleOption, SurveyType
from .rcdi_scoring import score_rcdi_session
from .result_display import build_development_result_context
from .ejs_result import build_ejs_result
from .ejs_text import is_ezhs_legacy_change_question, is_ezhs_satisfaction_question


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
        "title": "Опрос о повседневной жизни ребёнка (ЕЖС)",
        "body": [
            "Этот опрос поможет понять, как ваш ребёнок ведёт себя в обычных жизненных ситуациях: во время сна, еды, игры, прогулок и других повседневных дел.",
            "Здесь нет правильных или неправильных ответов — важно выбрать тот вариант, который лучше всего подходит вашему ребёнку.",
            "Как отвечать на вопросы:",
            "Для каждого утверждения выберите один вариант:",
            "• Часто — ребёнок делает это регулярно",
            "• Редко — делает иногда",
            "• Ещё не делает — пока не умеет или не делает",
            "• Уже не делает — раньше делал, но сейчас перерос",
            "Отвечайте, опираясь на поведение ребёнка в последнее время.",
            "Важно знать:",
            "• Вопросы уже подобраны с учётом возраста вашего ребёнка.",
            "• Некоторые навыки могут ещё не появиться — это нормально.",
            "• Опрос нужен для общего понимания развития, а не для постановки диагноза.",
            "Что вы получите в конце:",
            "После прохождения вы увидите:",
            "• разбор по разным сферам жизни ребёнка",
            "• где всё развивается нормально",
            "• где стоит обратить внимание",
            "• рекомендации, что делать дальше",
            "При необходимости вы сможете отправить результат специалисту.",
            "Перед началом:",
            "• Постарайтесь отвечать честно и внимательно.",
            "• Не пропускайте вопросы.",
            "• Опрос займёт немного времени.",
            "Нажмите «Начать опрос», чтобы перейти к вопросам.",
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
    if slug == "ezhs" and not (0 <= age <= 36):
        return False, "Опрос ЕЖС доступен для возраста от 0 до 36 месяцев."
    return True, ""


def _parse_ezhs_min_age(age_str: str | None) -> int | None:
    if not age_str:
        return None
    token = str(age_str).strip()
    if not token:
        return None
    if "-" in token:
        token = token.split("-", 1)[0].strip()
    try:
        return int(token)
    except ValueError:
        return None


def _ensure_ezhs_answer_options(question: Question):
    if is_ezhs_satisfaction_question(question.text):
        options = [(str(i), str(i)) for i in range(1, 6)]
    elif is_ezhs_legacy_change_question(question.text):
        # Не показываем в опросе; опции не трогаем агрессивно (PROTECT).
        return
    else:
        options = [
            ("Еще не делает", "not_yet"),
            ("Редко", "rare"),
            ("Часто", "often"),
            ("Уже не делает", "not_anymore"),
        ]
    # Исправляем legacy-варианты (Да/Нет/Иногда) на единый набор ЕЖС
    # без удаления (Answer.selected_option использует PROTECT).
    for i, (text, value) in enumerate(options, start=1):
        opt = question.answer_options.filter(order=i).first()
        if opt:
            changed = False
            if opt.text != text:
                opt.text = text
                changed = True
            if (opt.value or "") != value:
                opt.value = value
                changed = True
            if changed:
                opt.save(update_fields=["text", "value"])
        else:
            AnswerOption.objects.create(
                question=question,
                text=text,
                value=value,
                order=i,
            )


def _sanitize_ezhs_topic_questions(questions: list[Question]) -> list[Question]:
    """
    Убираем дубли сервисных вопросов и не показываем пустые рутины,
    в которых нет ни одного обычного (поведенческого) вопроса.
    """
    skill_questions = [
        q
        for q in questions
        if not is_ezhs_satisfaction_question(q.text) and not is_ezhs_legacy_change_question(q.text)
    ]
    if not skill_questions:
        return []

    sanitized = list(skill_questions)
    added_satisfaction = False
    for q in questions:
        if not is_ezhs_satisfaction_question(q.text):
            continue
        if added_satisfaction:
            continue
        added_satisfaction = True
        sanitized.append(q)
    return sorted(sanitized, key=lambda x: (x.order, x.id))


def _ezhs_routine_question_counts(session: SurveySession) -> dict:
    """Число обычных (поведенческих) вопросов по рутине с учётом возраста — для пустых рутин."""
    if not session.survey_type_id:
        return {}
    base_qs = Question.objects.filter(survey_type_id=session.survey_type_id, is_active=True)
    all_topics = []
    seen = set()
    for raw in base_qs.order_by("order", "id").values_list("category", flat=True):
        label = (raw or "").strip() or "Без категории"
        if label in seen:
            continue
        seen.add(label)
        all_topics.append(label)

    age = session.child_age_months
    eligible_qs = base_qs
    if age is not None:
        eligible_qs = eligible_qs.filter(age_min_months__lte=age)

    counts = {topic: 0 for topic in all_topics}
    for q in eligible_qs.only("category", "text"):
        if is_ezhs_satisfaction_question(q.text) or is_ezhs_legacy_change_question(q.text):
            continue
        label = (q.category or "").strip() or "Без категории"
        counts[label] = counts.get(label, 0) + 1
    return counts


def _ordered_topics_for_ezhs(base_qs):
    seen = set()
    result = []
    for raw in base_qs.order_by("order", "id").values_list("category", flat=True):
        raw_topic = raw or ""
        topic_key = raw_topic.strip() or "Без категории"
        if topic_key in seen:
            continue
        seen.add(topic_key)
        result.append({"raw": raw_topic, "label": topic_key})
    return result


def _dedupe_questions_by_order(base_qs):
    """
    Не меняем БД и не трогаем scoring-логику:
    для каждого order показываем один канонический вопрос (min id).
    """
    canonical_ids = base_qs.values("order").annotate(min_id=Min("id")).values_list("min_id", flat=True)
    return base_qs.filter(id__in=canonical_ids)


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

    # Если вопросы уже загружены в нашу модель, ничего не делаем.
    if Question.objects.filter(survey_type=survey_type).exists() and slug != "ezhs":
        return survey_type
    if slug == "ezhs":
        ezhs_qs = Question.objects.filter(survey_type=survey_type)
        # Не выполняем тяжелый update_or_create на каждый запрос, если данные уже готовы.
        if ezhs_qs.exists() and not ezhs_qs.filter(category="").exists() and not ezhs_qs.filter(
            age_min_months__isnull=True
        ).exists():
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
                cursor.execute(
                    "SELECT question_order, question, age, topic FROM ejs_questions ORDER BY question_order"
                )
                rows = cursor.fetchall()
                bulk = []
                for order, text, age_str, topic in rows:
                    age_min = _parse_ezhs_min_age(age_str)
                    bulk.append(
                        Question(
                            survey_type=survey_type,
                            text=text,
                            order=order or 0,
                            category=(topic or "").strip(),
                            is_active=True,
                            age_min_months=age_min,
                            age_max_months=None,
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
        if slug == "ezhs":
            for q in bulk:
                Question.objects.update_or_create(
                    survey_type=survey_type,
                    order=q.order,
                    text=q.text,
                    defaults={
                        "category": q.category,
                        "is_active": True,
                        "age_min_months": q.age_min_months,
                        "age_max_months": None,
                    },
                )
        else:
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

    guest_mode = not request.user.is_authenticated

    # Parent flow: child profile is required for all surveys.
    child_profile = None
    if not guest_mode and slug in ("kdi", "rcdi", "m-chat", "ezhs"):
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
        if guest_mode:
            guest_form = GuestSurveyStartForm(request.POST, survey_slug=slug)
            if guest_form.is_valid():
                birth_date = guest_form.cleaned_data["birth_date"]
                gender = guest_form.cleaned_data.get("gender")
                age_months = calculate_age_months_float(birth_date)
                ok, err_msg = _survey_age_allowed(slug, age_months)
                if not ok:
                    guest_form.add_error(None, err_msg)
                else:
                    session = SurveySession.objects.create(
                        user=None,
                        child_profile=None,
                        survey_type=survey_type,
                        child_age_months=age_months,
                        guest_birth_date=birth_date,
                        guest_gender=gender,
                    )
                    url = reverse("survey_page", args=[slug]) + f"?session_id={session.pk}"
                    return redirect(url)
        else:
            guest_form = None
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

    else:
        guest_form = GuestSurveyStartForm(survey_slug=slug) if guest_mode else None

    context = {
        "survey_slug": slug,
        "survey_title": title,
        "instruction_title": instruction["title"],
        "instruction_body": instruction["body"],
        "ask_age": ask_age,
        "age_error": age_error,
        "child_profile": child_profile,
        "guest_mode": guest_mode,
        "guest_form": guest_form,
        "guest_gender_required": slug == "rcdi",
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
            ).select_related("survey_type", "child_profile").first()
            if survey_session:
                ok, err_msg = _survey_age_allowed(slug, survey_session.child_age_months)
                if not ok:
                    messages.error(request, err_msg)
                    if request.user.is_authenticated:
                        return redirect("parent_dashboard")
                    return redirect(reverse("survey_start", args=[slug]))
        except ValueError:
            pass

    # Для опросников подтягиваем вопросы из существующих таблиц,
    # затем работаем через обычные Django-модели.
    survey_type = _ensure_questions_imported_from_legacy(slug)

    age_months: float | None = float(survey_session.child_age_months) if (
        survey_session and survey_session.child_age_months is not None
    ) else None
    age_error: str | None = None

    base_qs = Question.objects.filter(survey_type=survey_type, is_active=True) if survey_type else Question.objects.none()
    if survey_type and slug in ("kdi", "rcdi"):
        base_qs = base_qs.exclude(category="")
    # KID в текущей БД может содержать дубли по order.
    # Для прохождения показываем по одному вопросу на каждый номер.
    if slug == "kdi":
        base_qs = _dedupe_questions_by_order(base_qs)

    if slug == "ezhs":
        if not survey_session:
            messages.error(request, "Сначала начните опрос ЕЖС из карточки ребенка.")
            return redirect("parent_dashboard")
        if age_months is None:
            age_error = "Не удалось определить возраст ребенка."
            base_qs = Question.objects.none()
        else:
            base_qs = base_qs.filter(age_min_months__lte=age_months)

    # Пагинация: для ЕЖС по рутинам, для остальных по 20 вопросов.
    try:
        page = int(request.GET.get("page", request.POST.get("page", "1")))
    except (ValueError, TypeError):
        page = 1
    routine_page_name = None
    if slug == "ezhs":
        all_topic_items = _ordered_topics_for_ezhs(base_qs)
        topic_items = []
        topic_sizes = []
        for item in all_topic_items:
            topic_qs = base_qs.filter(category=item["raw"]).order_by("order", "id")
            sanitized_topic = _sanitize_ezhs_topic_questions(list(topic_qs))
            if sanitized_topic:
                topic_items.append(item)
                topic_sizes.append(len(sanitized_topic))
        total = sum(topic_sizes)
        total_pages = max(1, len(topic_items)) if topic_items else 1
        page = min(max(page, 1), total_pages)
        topic_item = topic_items[page - 1] if topic_items else None
        routine_page_name = topic_item["label"] if topic_item else None
        routine_page_raw = topic_item["raw"] if topic_item else None
        questions_qs = base_qs.filter(category=routine_page_raw).order_by("order", "id")
        questions = _sanitize_ezhs_topic_questions(list(
            questions_qs.prefetch_related(Prefetch("answer_options", queryset=AnswerOption.objects.all()))
        ))
        start = 0
        end = len(questions)
    else:
        per_page = 20
        total = base_qs.count()
        total_pages = max(1, ceil(total / per_page)) if total else 1
        page = min(max(page, 1), total_pages)
        start = (page - 1) * per_page
        end = start + per_page
        questions = list(
            base_qs.order_by("order", "id")
            .prefetch_related(Prefetch("answer_options", queryset=AnswerOption.objects.all()))[start:end]
        )

    # Scale options for KID/RCDI (1,2,3 with scores)
    scale_options = []
    if survey_type and slug in ("kdi", "rcdi"):
        scale_options = list(SurveyScaleOption.objects.filter(survey_type=survey_type).order_by("value"))

    if slug == "ezhs":
        for q in questions:
            _ensure_ezhs_answer_options(q)
            # В этой точке answer_options уже могли быть prefetched выше.
            # Сбрасываем кеш, чтобы шаблон сразу увидел только что созданные/обновленные опции.
            prefetched = getattr(q, "_prefetched_objects_cache", None)
            if isinstance(prefetched, dict):
                prefetched.pop("answer_options", None)
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
            elif slug == "ezhs":
                opt_id = request.POST.get(key)
                if not opt_id:
                    missing_questions.append(q.order)
                    continue
                try:
                    opt_id = int(opt_id)
                except (ValueError, TypeError):
                    missing_questions.append(q.order)
                    continue
                option = q.answer_options.filter(pk=opt_id).first()
                if not option:
                    missing_questions.append(q.order)
                    continue
                if is_ezhs_satisfaction_question(q.text):
                    raw_val = (option.value or option.text or "").strip()
                    if not raw_val.isdigit() or not (1 <= int(raw_val) <= 5):
                        missing_questions.append(q.order)
                        continue
                    sat = float(int(raw_val))
                    Answer.objects.update_or_create(
                        session=survey_session,
                        question=q,
                        defaults={
                            "selected_option": option,
                            "selected_scale_option": None,
                            "score": sat,
                        },
                    )
                else:
                    score_map = {"not_yet": 0.0, "rare": 1.0, "often": 2.0, "not_anymore": 3.0}
                    Answer.objects.update_or_create(
                        session=survey_session,
                        question=q,
                        defaults={
                            "selected_option": option,
                            "selected_scale_option": None,
                            "score": score_map.get((option.value or "").lower(), 0.0),
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
            missed = ", ".join(str(n) for n in sorted(set(missing_questions))[:8])
            suffix = f" (вопросы: {missed})" if missed else ""
            messages.error(request, f"Ответьте на все вопросы на странице перед продолжением{suffix}.")
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
        elif slug == "ezhs":
            routine_counts = _ezhs_routine_question_counts(survey_session)
            survey_session.total_score = None
            survey_session.risk_level = None
            survey_session.per_category_scores = None
            survey_session.per_category_status = None
            prior_disc = None
            old_pack = survey_session.ejs_routine_analysis
            if isinstance(old_pack, dict) and isinstance(old_pack.get("parent_discussion_requests"), dict):
                prior_disc = old_pack["parent_discussion_requests"]
            ezhs_pack = build_ejs_result(
                answers_for_score,
                routine_question_counts=routine_counts,
                parent_discussion_requests=prior_disc,
            )
            survey_session.ejs_routine_analysis = ezhs_pack
            survey_session.problematic_routines_count = int(ezhs_pack["problematic_routines_count"])
            survey_session.recommended_specialist_consultation = int(ezhs_pack["problematic_routines_count"]) >= 2
            survey_session.result_text = ezhs_pack["final_recommendation"]
        else:
            survey_session.total_score = float(total_score) if slug in ("ezhs", "m-chat") else None
            survey_session.risk_level = None
            survey_session.per_category_scores = None
            survey_session.per_category_status = None
            if slug == "m-chat":
                survey_session.result_text = "Опрос завершен. Результаты будут обработаны специалистом."
            else:
                survey_session.result_text = "Опрос завершён."
        save_fields = ["completed_at", "result_text", "total_score", "risk_level", "per_category_scores", "per_category_status"]
        if slug == "ezhs":
            save_fields.extend(["ejs_routine_analysis", "problematic_routines_count", "recommended_specialist_consultation"])
        survey_session.save(update_fields=save_fields)
        return redirect("survey_result", slug=slug, session_id=survey_session.pk)

    if slug == "ezhs":
        q_orders = [q.order for q in questions]
        first_index = min(q_orders) if q_orders else 0
        last_index = max(q_orders) if q_orders else 0
        progress_percent = int((page / total_pages) * 100) if total_pages else 0
    else:
        if slug == "m-chat" and survey_session:
            answered_on_survey = Answer.objects.filter(session=survey_session).count()
            progress_percent = int((answered_on_survey / total) * 100) if total else 0
        else:
            shown_until = min(end, total) if total else 0
            progress_percent = int((shown_until / total) * 100) if total else 0
        first_index = start + 1 if total else 0
        last_index = min(end, total) if total else 0

    child_summary = None
    if survey_session:
        if survey_session.child_profile:
            cp = survey_session.child_profile
            child_summary = {
                "name": cp.child_name,
                "age_months": survey_session.child_age_months,
                "gender": cp.gender,
            }
        else:
            child_summary = {
                "name": "Ребёнок",
                "age_months": survey_session.child_age_months,
                "gender": gender_for_display(survey_session.guest_gender),
            }

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
        "routine_page_name": routine_page_name,
        "child_summary": child_summary,
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
    )
    if request.user.is_authenticated and not _is_specialist(request.user):
        owner_ok = False
        if session.user_id and session.user_id == request.user.id:
            owner_ok = True
        if session.child_profile_id and session.child_profile and session.child_profile.parent_id == request.user.id:
            owner_ok = True
        if not owner_ok:
            return HttpResponseForbidden("Доступ запрещён.")
    if session.completed_at is None:
        messages.info(request, "Этот опрос ещё не завершён. Продолжите заполнение черновика.")
        return redirect(reverse("survey_page", args=[slug]) + f"?session_id={session.pk}")
    if request.method == "POST":
        if request.POST.get("consent") == "1":
            # Guest: не позволяем “мгновенно” отправить специалисту без анкеты/контактов.
            if session.user_id is None:
                has_child = bool(session.guest_child_profile_data)
                has_contact = bool(session.guest_contact_data)
                if not (has_child and has_contact):
                    messages.info(
                        request,
                        "Чтобы отправить результаты специалисту, необходимо заполнить анкету ребёнка и контактные данные.",
                    )
                    return redirect(reverse("guest_specialist_submit", args=[slug, session.pk]))

            session.consent_to_send = True
            session.save(update_fields=["consent_to_send"])
            return redirect("survey_result", slug=slug, session_id=session_id)
        if slug == "ezhs" and request.POST.get("ezhs_save_discussion") == "1":
            old = session.ejs_routine_analysis or {}
            stored = dict(old.get("parent_discussion_requests") or {})
            idx = 0
            while f"ezhs_discuss_name_{idx}" in request.POST:
                name = (request.POST.get(f"ezhs_discuss_name_{idx}") or "").strip()
                if name:
                    choice = (request.POST.get(f"ezhs_discuss_{idx}") or "").strip().lower()
                    if choice in ("yes", "да"):
                        stored[name] = True
                    elif choice in ("no", "нет"):
                        stored[name] = False
                idx += 1
            routine_counts = _ezhs_routine_question_counts(session)
            answers_qs = list(
                session.answers.select_related("question", "selected_option").order_by("question__order")
            )
            ezhs_pack = build_ejs_result(
                answers_qs,
                routine_question_counts=routine_counts,
                parent_discussion_requests=stored,
            )
            session.ejs_routine_analysis = ezhs_pack
            session.save(update_fields=["ejs_routine_analysis"])
            messages.success(request, "Ваш выбор сохранён.")
            return redirect("survey_result", slug=slug, session_id=session_id)

    context = {
        "survey_slug": slug,
        "survey_title": SURVEY_LABELS.get(slug, slug.upper()),
        "session": session,
        "guest_mode": session.user_id is None,
        "guest_has_child_anketa": bool(session.guest_child_profile_data),
        "guest_has_contact": bool(session.guest_contact_data),
    }
    context.update(build_development_result_context(session, slug))
    if slug == "ezhs":
        routine_counts = _ezhs_routine_question_counts(session)
        stored_disc = None
        if isinstance(session.ejs_routine_analysis, dict):
            dr = session.ejs_routine_analysis.get("parent_discussion_requests")
            if isinstance(dr, dict) and dr:
                stored_disc = dr
        ezhs_pack = build_ejs_result(
            list(session.answers.select_related("question", "selected_option").order_by("question__order")),
            routine_question_counts=routine_counts,
            parent_discussion_requests=stored_disc,
        )
        routines_list = ezhs_pack.get("routines", [])
        weak_routines = [
            r for r in routines_list if (not r.get("is_empty")) and r.get("status_code") != "calm"
        ]
        context.update(
            {
                "ezhs_result": ezhs_pack,
                "ezhs_routines": routines_list,
                "ezhs_weak_routines": weak_routines,
                "ezhs_problematic_count": ezhs_pack.get("problematic_routines_count", 0),
                "ezhs_final_recommendation": ezhs_pack.get("final_recommendation", session.result_text),
                "ezhs_key_signals": ezhs_pack.get("key_signals", {}),
                "ezhs_show_discussion_form": bool(weak_routines),
            }
        )
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


def guest_specialist_submit(request, slug: str, session_id: int):
    """
    Guest-only: форма анкеты ребёнка + контакты, после успешной отправки
    выставляем `consent_to_send=True`, чтобы специалист увидел кейс.
    """
    if _is_specialist(request.user):
        return redirect("specialist_dashboard")

    session = get_object_or_404(
        SurveySession.objects.select_related("survey_type"),
        pk=session_id,
        survey_type__slug=slug,
    )

    if session.user_id is not None:
        # Встроенная логика проекта ожидает отдельный кабинет для родителей.
        return HttpResponseForbidden("Доступ запрещён.")

    if session.completed_at is None:
        messages.info(request, "Сначала завершите опрос, чтобы перейти к отправке специалисту.")
        return redirect(reverse("survey_page", args=[slug]) + f"?session_id={session.pk}")

    if request.method == "POST":
        child_form = ChildProfileForm(request.POST)
        contact_form = GuestContactForm(request.POST)

        if child_form.is_valid() and contact_form.is_valid():
            cd = child_form.cleaned_data

            gender = cd.get("gender")  # male/female
            seizures = bool(cd.get("seizures"))
            birth_date = cd.get("birth_date")

            # Сохраняем "как для специалиста": человекочитаемые поля + сериализуем даты.
            guest_child_data = dict(cd)
            if birth_date:
                guest_child_data["birth_date"] = birth_date.isoformat()
            guest_child_data["seizures"] = seizures
            guest_child_data["gender"] = "Мужской" if gender == "male" else "Женский"

            session.guest_child_profile_data = guest_child_data
            session.guest_contact_data = contact_form.cleaned_data

            # Обновляем агрегированные guest-поля (используются для RCDI нормы).
            session.guest_birth_date = birth_date
            session.guest_gender = gender

            session.consent_to_send = True
            session.save(
                update_fields=[
                    "guest_child_profile_data",
                    "guest_contact_data",
                    "guest_birth_date",
                    "guest_gender",
                    "consent_to_send",
                ]
            )
            messages.success(request, "Спасибо! Мы сохранили анкету и контакты и отправили данные специалисту.")
            return redirect("survey_result", slug=slug, session_id=session.pk)
    else:
        initial = {}
        if session.guest_birth_date:
            initial["birth_date"] = session.guest_birth_date
        if session.guest_gender:
            initial["gender"] = session.guest_gender
        child_form = ChildProfileForm(initial=initial)

        contact_initial = session.guest_contact_data if isinstance(session.guest_contact_data, dict) else {}
        contact_form = GuestContactForm(initial=contact_initial)

    return render(
        request,
        "surveys/guest_specialist_submit.html",
        {
            "survey_slug": slug,
            "session": session,
            "child_form": child_form,
            "contact_form": contact_form,
        },
    )


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
            or (s.survey_type.slug == "ezhs" and (s.problematic_routines_count or 0) >= 2)
            or ("зона риска" in (s.per_category_status or {}).values())
        ]
    elif risk_filter == "borderline":
        sessions = [
            s for s in sessions
            if (s.survey_type.slug == "m-chat" and s.risk_level == "medium")
            or (s.survey_type.slug == "ezhs" and (s.problematic_routines_count or 0) == 1)
            or ("пограничное состояние" in (s.per_category_status or {}).values())
        ]
    elif risk_filter == "normal":
        sessions = [
            s for s in sessions
            if (s.survey_type.slug == "m-chat" and s.risk_level == "low")
            or (s.survey_type.slug == "ezhs" and (s.problematic_routines_count or 0) == 0)
            or (s.per_category_status and all(v == "норма" for v in (s.per_category_status or {}).values()))
        ]

    for s in sessions:
        if s.survey_type.slug == "m-chat" and s.risk_level:
            s.risk_level = s.risk_level
            continue
        if s.survey_type.slug == "ezhs":
            if (s.problematic_routines_count or 0) >= 2:
                s.risk_level = "risk"
            elif (s.problematic_routines_count or 0) == 1:
                s.risk_level = "borderline"
            else:
                s.risk_level = "normal"
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
    elif session.survey_type.slug == "ezhs":
        stored_disc = None
        if isinstance(session.ejs_routine_analysis, dict):
            dr = session.ejs_routine_analysis.get("parent_discussion_requests")
            if isinstance(dr, dict) and dr:
                stored_disc = dr
        ezhs_pack = build_ejs_result(
            list(session.answers.select_related("question", "selected_option").all()),
            routine_question_counts=_ezhs_routine_question_counts(session),
            parent_discussion_requests=stored_disc,
        )
    else:
        ezhs_pack = None

    context = {
        "session": session,
        "detail_rows": detail_rows,
        "mchat_failed_answers": mchat_failed_answers,
        "answer_rows": answer_rows,
        "ezhs_result": ezhs_pack if session.survey_type.slug == "ezhs" else None,
    }
    return render(request, "specialist/case_detail.html", context)


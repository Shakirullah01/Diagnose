"""
Создаёт завершённые сессии KID/RCDI со случайными (или заданным паттерном) ответами,
чтобы смотреть страницу результатов без ручного прохождения опроса.

  python manage.py seed_dummy_survey_sessions
  python manage.py seed_dummy_survey_sessions --survey kdi --pattern normal --age-months 8
  python manage.py seed_dummy_survey_sessions --survey rcdi --pattern risk --sex F
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from surveys.kid_scoring import score_kid_session
from surveys.models import Answer, Question, SurveyScaleOption, SurveySession, SurveyType
from surveys.rcdi_scoring import score_rcdi_session

try:
    from accounts.models import User
except Exception:  # pragma: no cover
    User = None


def _birth_date_for_age_months(age_months: float) -> date:
    days = int(round(float(age_months) * (365.25 / 12)))
    return date.today() - timedelta(days=days)


def _pick_scale_option(scale_by_value: dict[int, SurveyScaleOption], pattern: str, rng: random.Random) -> SurveyScaleOption:
    """Шкала 1/2 → балл 1, 3 → 0 (как в импорте)."""
    o1, o2, o3 = scale_by_value[1], scale_by_value[2], scale_by_value[3]
    if pattern == "normal":
        return rng.choice([o1, o2])
    if pattern == "risk":
        return o3
    if pattern == "borderline":
        return rng.choice([o2, o3])
    if pattern == "random":
        return rng.choice([o1, o2, o3])
    # mixed: чаще «норма», но есть разброс
    return rng.choices([o1, o2, o3], weights=[0.45, 0.35, 0.2], k=1)[0]


class Command(BaseCommand):
    help = "Создать тестовые завершённые сессии KID/RCDI с ответами для просмотра результатов."

    def add_arguments(self, parser):
        parser.add_argument(
            "--survey",
            choices=("kdi", "rcdi", "both"),
            default="both",
            help="Какой опрос заполнить",
        )
        parser.add_argument(
            "--pattern",
            choices=("normal", "mixed", "risk", "borderline", "random"),
            default="mixed",
            help="normal — в основном 1–2; risk — везде 3; mixed/random — вариативно",
        )
        parser.add_argument(
            "--age-months",
            type=float,
            default=None,
            help="Возраст для сессии (по умолчанию: KID 8, RCDI 24)",
        )
        parser.add_argument(
            "--sex",
            choices=("M", "F"),
            default="M",
            help="Пол ребёнка (для RCDI и анкеты)",
        )
        parser.add_argument(
            "--email",
            default="dummy-parent@example.com",
            help="Email пользователя-родителя (создаётся, если нет)",
        )
        parser.add_argument(
            "--password",
            default="testpass123",
            help="Пароль для нового пользователя",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Seed RNG для воспроизводимых ответов",
        )

    def handle(self, *args, **options):
        if User is None:
            self.stderr.write("Модель User недоступна.")
            return

        survey = options["survey"]
        pattern = options["pattern"]
        sex = options["sex"]
        email = options["email"]
        password = options["password"]
        seed = options["seed"]
        rng = random.Random(seed)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": "Тест",
                "last_name": "Родитель",
                "role": User.ROLE_PARENT,
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS(f"Создан пользователь {email} (пароль: {password})"))
        else:
            self.stdout.write(f"Пользователь {email} уже есть.")

        from children.models import ChildProfile

        gender_label = "мальчик" if sex == "M" else "девочка"
        age_kid = options["age_months"] if options["age_months"] is not None else 8.0
        age_rcdi = options["age_months"] if options["age_months"] is not None else 24.0

        profile, p_created = ChildProfile.objects.get_or_create(
            parent=user,
            child_name="Тестовый ребёнок (dummy)",
            defaults={
                "birth_date": _birth_date_for_age_months(age_kid if survey in ("kdi", "both") else age_rcdi),
                "gender": gender_label,
            },
        )
        if p_created:
            self.stdout.write(self.style.SUCCESS("Создана анкета ребёнка."))
        else:
            profile.birth_date = _birth_date_for_age_months(age_kid if survey in ("kdi", "both") else age_rcdi)
            profile.gender = gender_label
            profile.save(update_fields=["birth_date", "gender"])

        urls = []
        with transaction.atomic():
            if survey in ("kdi", "both"):
                sid = self._seed_one(
                    slug="kdi",
                    user=user,
                    profile=profile,
                    age_months=age_kid,
                    pattern=pattern,
                    rng=rng,
                )
                urls.append(f"  KID:  /surveys/kdi/result/{sid}/")
            if survey in ("rcdi", "both"):
                sid = self._seed_one(
                    slug="rcdi",
                    user=user,
                    profile=profile,
                    age_months=age_rcdi,
                    pattern=pattern,
                    rng=rng,
                )
                urls.append(f"  RCDI: /surveys/rcdi/result/{sid}/")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Готово. Откройте в браузере (войдите как этот родитель):"))
        for u in urls:
            self.stdout.write(u)

    def _seed_one(
        self,
        *,
        slug: str,
        user,
        profile,
        age_months: float,
        pattern: str,
        rng: random.Random,
    ) -> int:
        st = SurveyType.objects.filter(slug=slug).first()
        if not st:
            raise SystemExit(f"Нет SurveyType со slug={slug!r}. Сначала import_survey_data.")

        questions = list(
            Question.objects.filter(survey_type=st, is_active=True)
            .exclude(category="")
            .order_by("order", "id")
        )
        if not questions:
            raise SystemExit(f"Нет вопросов с категорией для {slug}. Запустите: python manage.py import_survey_data")

        scale = list(SurveyScaleOption.objects.filter(survey_type=st).order_by("value"))
        if len(scale) < 3:
            raise SystemExit(f"Нет шкалы ответов для {slug}. Запустите import_survey_data.")

        scale_by_value = {o.value: o for o in scale}

        session = SurveySession.objects.create(
            user=user,
            child_profile=profile,
            survey_type=st,
            child_age_months=float(age_months),
            completed_at=timezone.now(),
        )

        answers = []
        for q in questions:
            opt = _pick_scale_option(scale_by_value, pattern, rng)
            answers.append(
                Answer(
                    session=session,
                    question=q,
                    selected_scale_option=opt,
                    score=float(opt.score),
                )
            )
        Answer.objects.bulk_create(answers)

        answers_db = list(session.answers.select_related("question"))
        total = session.answers.aggregate(s=Sum("score"))["s"] or 0
        session.total_score = float(total)

        if slug == "kdi":
            pack = score_kid_session(session, answers_db)
        else:
            pack = score_rcdi_session(session, answers_db)

        session.per_category_scores = pack["per_category_scores"]
        session.per_category_status = pack["per_category_status"]
        session.result_text = pack["final_conclusion"]
        session.save(
            update_fields=[
                "total_score",
                "per_category_scores",
                "per_category_status",
                "result_text",
            ]
        )

        self.stdout.write(
            f"{slug.upper()}: сессия id={session.pk}, вопросов={len(questions)}, "
            f"балл={session.total_score}, заключение: {session.result_text[:60]}…"
        )
        return session.pk

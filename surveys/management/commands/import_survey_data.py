import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from surveys.models import KidNorm, Question, RCDINorm, SurveyScaleOption, SurveyType


def _project_root() -> Path:
    return Path(settings.BASE_DIR).resolve()


def _read_csv(name: str) -> list[dict]:
    path = _project_root() / name
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _first_existing(*names: str) -> Path | None:
    for name in names:
        p = _project_root() / name
        if p.is_file():
            return p
    return None


class Command(BaseCommand):
    help = "Импорт вопросов и норм KID/RCDI из CSV в корне проекта."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-norms",
            action="store_true",
            help="Удалить существующие KidNorm и RCDINorm перед загрузкой",
        )

    def handle(self, *args, **options):
        clear_norms = options["clear_norms"]
        with transaction.atomic():
            self._import_kid_questions()
            self._import_rcdi_questions()
            if clear_norms:
                KidNorm.objects.all().delete()
                RCDINorm.objects.all().delete()
            self._import_kid_norms()
            self._import_rcdi_norms()
            self._ensure_scale_options()
        self.stdout.write(self.style.SUCCESS("Импорт завершён."))

    def _ensure_scale_options(self):
        for slug, name in [("kdi", "КИД"), ("rcdi", "RCDI")]:
            st, _ = SurveyType.objects.get_or_create(slug=slug, defaults={"name": name})
            if not SurveyScaleOption.objects.filter(survey_type=st).exists():
                SurveyScaleOption.objects.bulk_create(
                    [
                        SurveyScaleOption(
                            survey_type=st,
                            value=1,
                            text="ребёнок начал выполнять это действие в течение последнего месяца",
                            score=1,
                        ),
                        SurveyScaleOption(
                            survey_type=st,
                            value=2,
                            text="ребёнок выполняет это действие уже давно (более месяца)",
                            score=1,
                        ),
                        SurveyScaleOption(
                            survey_type=st,
                            value=3,
                            text="ребёнок пока не выполняет это действие",
                            score=0,
                        ),
                    ]
                )
                self.stdout.write(f"Добавлена шкала ответов для {slug}.")

    def _import_kid_questions(self):
        rows = _read_csv("kid_questions_with_categories.csv")
        if not rows:
            self.stdout.write(self.style.WARNING("Файл kid_questions_with_categories.csv не найден или пуст."))
            return
        st, _ = SurveyType.objects.get_or_create(slug="kdi", defaults={"name": "КИД"})
        for row in rows:
            order_raw = (row.get("order") or "").strip()
            text = (row.get("question") or row.get("question_text") or "").strip()
            cat_y = (row.get("category_y") or "").strip().upper()
            cat_x = (row.get("category_x") or "").strip().upper()
            category = cat_y or cat_x
            if not text or not order_raw:
                continue
            try:
                order = int(float(order_raw))
            except ValueError:
                continue
            if not category:
                continue
            Question.objects.update_or_create(
                survey_type=st,
                order=order,
                category=category,
                defaults={
                    "text": text,
                    "is_active": True,
                },
            )
        self.stdout.write(f"KID: обновлены вопросы ({len(rows)} строк в файле).")

    def _import_rcdi_questions(self):
        path = _first_existing("rcdi_questions_with_categories.csv", "rcdi_questions_with_categories .csv")
        if not path:
            self.stdout.write(self.style.WARNING("Файл rcdi_questions_with_categories.csv не найден."))
            return
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        st, _ = SurveyType.objects.get_or_create(slug="rcdi", defaults={"name": "RCDI"})
        for row in rows:
            order_raw = (row.get("order") or "").strip()
            text = (row.get("question") or row.get("question_text") or "").strip()
            category = (row.get("category") or "").strip().upper()
            if not text or not order_raw or not category:
                continue
            try:
                order = int(float(order_raw))
            except ValueError:
                continue
            Question.objects.update_or_create(
                survey_type=st,
                order=order,
                category=category,
                defaults={
                    "text": text,
                    "is_active": True,
                },
            )
        self.stdout.write(f"RCDI: обновлены вопросы ({len(rows)} строк в файле).")

    def _import_kid_norms(self):
        rows = _read_csv("kid_norms.csv")
        if not rows:
            self.stdout.write(self.style.WARNING("Файл kid_norms.csv не найден или пуст."))
            return
        bulk = []
        for row in rows:
            try:
                age = float((row.get("age_months") or "").replace(",", "."))
            except ValueError:
                continue
            cat = (row.get("area") or row.get("category") or "").strip().upper()
            if not cat:
                continue
            try:
                normal = float(row.get("normal") or 0)
                warning = float(row.get("warning") or 0)
                low = float(row.get("low") or 0)
            except ValueError:
                continue
            bulk.append(
                KidNorm(
                    age_months=age,
                    category=cat,
                    normal=normal,
                    warning=warning,
                    low=low,
                )
            )
        KidNorm.objects.all().delete()
        KidNorm.objects.bulk_create(bulk, batch_size=500)
        self.stdout.write(f"KID: загружено норм: {len(bulk)}.")

    def _import_rcdi_norms(self):
        path = _first_existing("rcdi_norms.csv", "cdi_norms.csv")
        if not path:
            self.stdout.write(self.style.WARNING("Файл rcdi_norms.csv / cdi_norms.csv не найден."))
            return
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        bulk = []
        for row in rows:
            try:
                age = float((row.get("age_months") or "").replace(",", "."))
            except ValueError:
                continue
            sex = (row.get("sex") or "").strip().upper()[:1]
            if sex not in ("M", "F"):
                continue
            cat = (row.get("area") or row.get("category") or "").strip().upper()
            if not cat:
                continue
            try:
                normal = float(row.get("normal") or 0)
                warning = float(row.get("warning") or 0)
                low = float(row.get("low") or 0)
            except ValueError:
                continue
            bulk.append(
                RCDINorm(
                    age_months=age,
                    sex=sex,
                    category=cat,
                    normal=normal,
                    warning=warning,
                    low=low,
                )
            )
        RCDINorm.objects.all().delete()
        RCDINorm.objects.bulk_create(bulk, batch_size=500)
        self.stdout.write(f"RCDI: загружено норм: {len(bulk)} (из {path.name}).")

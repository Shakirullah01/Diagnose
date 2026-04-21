import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from surveys.models import KidNorm, Question, RCDINorm, SurveyScaleOption, SurveyType


def _project_root() -> Path:
    return Path(settings.BASE_DIR).resolve()


def _system_data_dir() -> Path:
    return _project_root() / "data" / "system"


def _resolve_csv(*names: str) -> Path | None:
    """Prefer packaged CSV under data/system/, then project root."""
    for name in names:
        for base in (_system_data_dir(), _project_root()):
            p = base / name
            if p.is_file():
                return p
    return None


def _read_csv_rows(*names: str) -> tuple[list[dict], Path | None]:
    path = _resolve_csv(*names)
    if not path:
        return [], None
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f)), path


def _truncate_category(value: str, max_len: int = 10) -> str:
    s = (value or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len]


def _upsert_question_by_lookup(*, survey_type: SurveyType, lookup: dict, defaults: dict) -> None:
    """Create or update one row; if duplicates exist, update the oldest and leave others (dev DB safety)."""
    qs = Question.objects.filter(survey_type=survey_type, **lookup).order_by("id")
    first = qs.first()
    if first is None:
        Question.objects.create(survey_type=survey_type, **lookup, **defaults)
        return
    for k, v in defaults.items():
        setattr(first, k, v)
    first.save()


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


class Command(BaseCommand):
    help = (
        "Импорт системных данных опросов (KID/RCDI/M-CHAT/ЕЖС) и норм из CSV. "
        "Файлы ищутся в data/system/, затем в корне проекта. "
        "Не импортирует пользователей, сессии и ответы."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-norms",
            action="store_true",
            help="Удалить существующие KidNorm и RCDINorm перед загрузкой норм",
        )

    def handle(self, *args, **options):
        clear_norms = options["clear_norms"]
        with transaction.atomic():
            self._import_kid_questions()
            self._import_rcdi_questions()
            self._import_mchat_questions()
            self._import_ejs_questions()
            if clear_norms:
                KidNorm.objects.all().delete()
                RCDINorm.objects.all().delete()
            self._import_kid_norms()
            self._import_rcdi_norms()
            self._ensure_scale_options()
        self.stdout.write(self.style.SUCCESS("Импорт системных данных опросов завершён."))

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
        rows, path = _read_csv_rows("kid_questions_with_categories.csv")
        if not rows:
            self.stdout.write(self.style.WARNING("Файл kid_questions_with_categories.csv не найден или пуст."))
            return
        st, _ = SurveyType.objects.get_or_create(slug="kdi", defaults={"name": "КИД"})
        for row in rows:
            order_raw = (row.get("order") or "").strip()
            text = (row.get("question") or row.get("question_text") or "").strip()
            cat_y = (row.get("category_y") or "").strip().upper()
            cat_x = (row.get("category_x") or "").strip().upper()
            category = _truncate_category(cat_y or cat_x)
            if not text or not order_raw:
                continue
            try:
                order = int(float(order_raw))
            except ValueError:
                continue
            if not category:
                continue
            _upsert_question_by_lookup(
                survey_type=st,
                lookup={"order": order, "category": category},
                defaults={"text": text, "is_active": True},
            )
        self.stdout.write(f"KID: обновлены вопросы ({len(rows)} строк) из {path.name}.")

    def _import_rcdi_questions(self):
        rows, path = _read_csv_rows("rcdi_questions_with_categories.csv", "rcdi_questions_with_categories .csv")
        if not rows:
            self.stdout.write(self.style.WARNING("Файл rcdi_questions_with_categories.csv не найден."))
            return
        st, _ = SurveyType.objects.get_or_create(slug="rcdi", defaults={"name": "RCDI"})
        for row in rows:
            order_raw = (row.get("order") or "").strip()
            text = (row.get("question") or row.get("question_text") or "").strip()
            category = _truncate_category((row.get("category") or "").strip().upper())
            if not text or not order_raw or not category:
                continue
            try:
                order = int(float(order_raw))
            except ValueError:
                continue
            _upsert_question_by_lookup(
                survey_type=st,
                lookup={"order": order, "category": category},
                defaults={"text": text, "is_active": True},
            )
        self.stdout.write(f"RCDI: обновлены вопросы ({len(rows)} строк) из {path.name}.")

    def _import_mchat_questions(self):
        rows, path = _read_csv_rows("mchat_questions.csv")
        if not rows:
            self.stdout.write(self.style.WARNING("Файл mchat_questions.csv не найден или пуст."))
            return
        st, _ = SurveyType.objects.get_or_create(slug="m-chat", defaults={"name": "M-CHAT"})
        for row in rows:
            order_raw = (row.get("question_order") or row.get("order") or "").strip()
            text = (row.get("question") or row.get("question_text") or "").strip()
            if not text or not order_raw:
                continue
            try:
                order = int(float(order_raw))
            except ValueError:
                continue
            _upsert_question_by_lookup(
                survey_type=st,
                lookup={"order": order},
                defaults={
                    "text": text,
                    "is_active": True,
                    "category": "",
                },
            )
        self.stdout.write(f"M-CHAT: обновлены вопросы ({len(rows)} строк) из {path.name}.")

    def _import_ejs_questions(self):
        rows, path = _read_csv_rows("ejs_questions.csv")
        if not rows:
            self.stdout.write(self.style.WARNING("Файл ejs_questions.csv не найден или пуст."))
            return
        st, _ = SurveyType.objects.get_or_create(slug="ezhs", defaults={"name": "ЕЖС"})
        for row in rows:
            order_raw = (row.get("question_order") or row.get("order") or "").strip()
            text = (row.get("question") or row.get("question_text") or "").strip()
            topic = (row.get("topic") or "").strip()
            age_min = _parse_ezhs_min_age(row.get("age"))
            if not text or not order_raw:
                continue
            try:
                order = int(float(order_raw))
            except ValueError:
                continue
            _upsert_question_by_lookup(
                survey_type=st,
                lookup={"order": order, "text": text},
                defaults={
                    "category": _truncate_category(topic),
                    "is_active": True,
                    "age_min_months": age_min,
                    "age_max_months": None,
                },
            )
        self.stdout.write(f"ЕЖС: обновлены вопросы ({len(rows)} строк) из {path.name}.")

    def _import_kid_norms(self):
        rows, path = _read_csv_rows("kid_norms.csv")
        if not rows:
            self.stdout.write(self.style.WARNING("Файл kid_norms.csv не найден или пуст."))
            return
        bulk = []
        for row in rows:
            try:
                age = float((row.get("age_months") or "").replace(",", "."))
            except ValueError:
                continue
            cat = _truncate_category((row.get("area") or row.get("category") or "").strip().upper())
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
        self.stdout.write(f"KID: загружено норм: {len(bulk)} (из {path.name}).")

    def _import_rcdi_norms(self):
        rows, path = _read_csv_rows("rcdi_norms.csv", "cdi_norms.csv")
        if not rows:
            self.stdout.write(self.style.WARNING("Файл rcdi_norms.csv / cdi_norms.csv не найден."))
            return
        bulk = []
        for row in rows:
            try:
                age = float((row.get("age_months") or "").replace(",", "."))
            except ValueError:
                continue
            sex = (row.get("sex") or "").strip().upper()[:1]
            if sex not in ("M", "F"):
                continue
            cat = _truncate_category((row.get("area") or row.get("category") or "").strip().upper())
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

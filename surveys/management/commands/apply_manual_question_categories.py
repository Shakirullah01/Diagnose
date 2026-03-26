from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import ProtectedError

from surveys.models import Question, SurveyType


def _expand(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a.strip())
            end = int(b.strip())
            if end < start:
                start, end = end, start
            out.update(range(start, end + 1))
        else:
            out.add(int(part))
    return out


RCDI_MAP = {
    "SO": _expand("1-40"),
    "SE": _expand("41-80"),
    "GR": _expand("81-110"),
    "FI": _expand("111-140"),
    "EX": _expand("4,6,11,37,141-177"),
    "LA": _expand("162,178-216"),
}

KID_MAP = {
    "F": _expand("1-252"),
    "COG": _expand(
        "6,16-18,26,27,37-39,46,50-52,62,63,65,73-75,79,88,89,95,105,106,116,127-129,"
        "142,144,154,181,186-188,200-204,214,215,218,226-228,235,236,245,246,249"
    ),
    "MOT": _expand(
        "8-11,22,31,32,42-45,55-58,68,69,80-82,87,94,96,97,109-112,120-124,132-136,146-149,"
        "157-160,167,171-175,183,184,190-193,207-211,217,219-222,229-232,238-242,247"
    ),
    "LAN": _expand("7,19,20,28-30,40,41,53,54,66,67,72,76-78,84,91-93,103,107,108,118,119,130,131,145,155,156,168,169,182,189,205,206,216,237"),
    "SEL": _expand("1-3,12,21,23,33,34,47,59,70,71,83,98-100,113,114,117,125,150,161,162,176,177,194-197,212,223,233,234,243,244,248,250,251,252"),
    "SOC": _expand("4,5,13,14,15,20,24,25,30,35,36,39,48,49,53,60,61,64,85,86,90,101-104,115,126,137-141,143,151-153,163-166,168,170,178,179,180,185,198,199,213,224,225"),
}


class Command(BaseCommand):
    help = "Apply manual KID/RCDI category mapping by question order and clean legacy duplicates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--drop-legacy-tables",
            action="store_true",
            help="Drop legacy raw tables: kdi_questions, rcdi_questions, ejs_questions, m_chat_questions.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        kdi = SurveyType.objects.get(slug="kdi")
        rcdi = SurveyType.objects.get(slug="rcdi")

        self._apply_for_slug("kdi", kdi, KID_MAP)
        self._apply_for_slug("rcdi", rcdi, RCDI_MAP)

        if options["drop_legacy_tables"]:
            self._drop_legacy_tables()

        self.stdout.write(self.style.SUCCESS("Manual category mapping applied successfully."))

    def _apply_for_slug(self, slug: str, st: SurveyType, mapping: dict[str, set[int]]):
        qs = Question.objects.filter(survey_type=st).order_by("order", "id")
        by_order: dict[int, list[Question]] = {}
        for q in qs:
            by_order.setdefault(q.order, []).append(q)

        updated = 0
        deleted_uncat = 0
        archived_uncat = 0

        for category, numbers in mapping.items():
            for num in numbers:
                rows = by_order.get(num, [])
                if not rows:
                    continue
                preferred = None
                for r in rows:
                    if r.category:
                        preferred = r
                        break
                if preferred is None:
                    preferred = rows[0]
                if preferred.category != category:
                    preferred.category = category
                    preferred.save(update_fields=["category"])
                    updated += 1

        # Keep only categorized rows for KID/RCDI question banks; remove blank duplicate records
        for q in Question.objects.filter(survey_type=st, category=""):
            if not Question.objects.filter(survey_type=st, order=q.order).exclude(pk=q.pk).exclude(category="").exists():
                continue
            try:
                q.delete()
                deleted_uncat += 1
            except ProtectedError:
                if q.is_active:
                    q.is_active = False
                    q.save(update_fields=["is_active"])
                    archived_uncat += 1

        total = Question.objects.filter(survey_type=st).count()
        with_cat = Question.objects.filter(survey_type=st).exclude(category="").count()
        self.stdout.write(
            f"{slug.upper()}: updated={updated}, deleted_uncategorized_duplicates={deleted_uncat}, archived_uncategorized={archived_uncat}, total={total}, with_category={with_cat}"
        )

    def _drop_legacy_tables(self):
        tables = ("kdi_questions", "rcdi_questions", "ejs_questions", "m_chat_questions")
        with connection.cursor() as cursor:
            for name in tables:
                cursor.execute(f'DROP TABLE IF EXISTS "{name}"')
                self.stdout.write(f"Dropped legacy table: {name}")

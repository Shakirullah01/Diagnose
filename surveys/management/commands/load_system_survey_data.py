from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Загрузить системные данные опросов из CSV (см. data/system/). "
        "Варианты ответов анкеты ребёнка заданы в модели ChildProfile (choices) — отдельный импорт не требуется."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-norms",
            action="store_true",
            help="Перед загрузкой норм удалить существующие KidNorm и RCDINorm",
        )

    def handle(self, *args, **options):
        call_command("import_survey_data", clear_norms=options["clear_norms"])

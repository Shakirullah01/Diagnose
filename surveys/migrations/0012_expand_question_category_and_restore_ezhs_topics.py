import csv
from pathlib import Path

from django.db import migrations, models


def restore_ezhs_topics(apps, schema_editor):
    Question = apps.get_model("surveys", "Question")
    SurveyType = apps.get_model("surveys", "SurveyType")

    survey_type = SurveyType.objects.filter(slug="ezhs").first()
    if survey_type is None:
        return

    base_dir = Path(__file__).resolve().parents[3]
    csv_path = base_dir / "data" / "system" / "ejs_questions.csv"
    if not csv_path.exists():
        return

    topic_by_key = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            text = (row.get("question") or row.get("question_text") or "").strip()
            order_raw = (row.get("question_order") or row.get("order") or "").strip()
            topic = (row.get("topic") or "").strip()
            if not text or not order_raw:
                continue
            try:
                order = int(float(order_raw))
            except ValueError:
                continue
            key = (order, text)
            if key not in topic_by_key:
                topic_by_key[key] = topic

    if not topic_by_key:
        return

    changed = []
    qs = Question.objects.filter(survey_type=survey_type).only("id", "order", "text", "category")
    for question in qs:
        topic = topic_by_key.get((question.order, (question.text or "").strip()))
        if topic is None:
            continue
        if (question.category or "") == topic:
            continue
        question.category = topic
        changed.append(question)

    if changed:
        Question.objects.bulk_update(changed, ["category"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0011_surveysession_ejs_analysis_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="category",
            field=models.CharField(blank=True, db_index=True, max_length=255, verbose_name="Категория"),
        ),
        migrations.RunPython(restore_ezhs_topics, migrations.RunPython.noop),
    ]


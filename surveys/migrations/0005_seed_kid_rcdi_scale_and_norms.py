from django.db import migrations


def seed_scale_and_norms(apps, schema_editor):
    SurveyType = apps.get_model("surveys", "SurveyType")
    SurveyScaleOption = apps.get_model("surveys", "SurveyScaleOption")
    KidNorms = apps.get_model("surveys", "KidNorms")

    for slug, name in [("kdi", "КИД"), ("rcdi", "RCDI")]:
        st, _ = SurveyType.objects.get_or_create(slug=slug, defaults={"name": name})
        if not SurveyScaleOption.objects.filter(survey_type=st).exists():
            SurveyScaleOption.objects.bulk_create([
                SurveyScaleOption(survey_type=st, value=1, text="ребёнок начал выполнять это действие в течение последнего месяца", score=1),
                SurveyScaleOption(survey_type=st, value=2, text="ребёнок выполняет это действие уже давно (более месяца)", score=1),
                SurveyScaleOption(survey_type=st, value=3, text="ребёнок пока не выполняет это действие", score=0),
            ])

    if not KidNorms.objects.exists():
        KidNorms.objects.bulk_create([
            KidNorms(age_months=2, normal_score=32, mild_delay_score=28),
            KidNorms(age_months=4, normal_score=80, mild_delay_score=70),
            KidNorms(age_months=6, normal_score=120, mild_delay_score=105),
            KidNorms(age_months=8, normal_score=158, mild_delay_score=138),
            KidNorms(age_months=10, normal_score=190, mild_delay_score=165),
            KidNorms(age_months=12, normal_score=220, mild_delay_score=190),
            KidNorms(age_months=14, normal_score=245, mild_delay_score=212),
            KidNorms(age_months=16, normal_score=265, mild_delay_score=230),
        ])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("surveys", "0004_scale_options_norms_session_age_answer_score"),
    ]

    operations = [
        migrations.RunPython(seed_scale_and_norms, noop),
    ]

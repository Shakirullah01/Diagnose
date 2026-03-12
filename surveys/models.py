from django.conf import settings
from django.db import models

from children.models import Child


class SurveyType(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Question(models.Model):
    survey_type = models.ForeignKey(SurveyType, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
     # Для опросников с возрастной градацией (например, ЕЖС)
    age_min_months = models.PositiveSmallIntegerField(null=True, blank=True)
    age_max_months = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.survey_type.slug}: {self.text[:60]}"


class AnswerOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answer_options")
    text = models.CharField(max_length=200)
    value = models.CharField(max_length=50, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.text


class SurveySession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    child = models.ForeignKey(Child, on_delete=models.SET_NULL, null=True, blank=True, related_name="survey_sessions")
    survey_type = models.ForeignKey(SurveyType, on_delete=models.PROTECT)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    final_score = models.FloatField(null=True, blank=True, verbose_name="Итоговый балл")
    result_text = models.TextField(blank=True, verbose_name="Заключение")
    consent_to_send = models.BooleanField(default=False, verbose_name="Согласие на отправку специалисту")

    STATUS_NEW = "new"
    STATUS_VIEWED = "viewed"
    STATUS_CHOICES = [
        (STATUS_NEW, "Новый"),
        (STATUS_VIEWED, "Просмотрено"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        verbose_name="Статус",
    )

    def __str__(self) -> str:
        return f"{self.survey_type.slug} ({self.started_at:%Y-%m-%d})"


class Answer(models.Model):
    session = models.ForeignKey(SurveySession, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    selected_option = models.ForeignKey(AnswerOption, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("session", "question"),)

    def __str__(self) -> str:
        return f"Answer({self.session_id}, q={self.question_id})"


class SpecialistNote(models.Model):
    survey_session = models.ForeignKey(SurveySession, on_delete=models.CASCADE, related_name="notes")
    specialist = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="specialist_notes")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    recommendation = models.TextField(blank=True, verbose_name="Рекомендация для родителей")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Note for session {self.survey_session_id} by {self.specialist_id}"


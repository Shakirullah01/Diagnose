from django.conf import settings
from django.db import models


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
    survey_type = models.ForeignKey(SurveyType, on_delete=models.PROTECT)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

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


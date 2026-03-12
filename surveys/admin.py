from django.contrib import admin

from .models import Answer, AnswerOption, Question, SurveySession, SurveyType


@admin.register(SurveyType)
class SurveyTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("survey_type", "order", "is_active", "text")
    list_filter = ("survey_type", "is_active")
    search_fields = ("text",)


@admin.register(AnswerOption)
class AnswerOptionAdmin(admin.ModelAdmin):
    list_display = ("question", "order", "text", "value")
    search_fields = ("text", "value")


@admin.register(SurveySession)
class SurveySessionAdmin(admin.ModelAdmin):
    list_display = ("survey_type", "user", "started_at", "completed_at")
    list_filter = ("survey_type", "completed_at")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("session", "question", "selected_option", "created_at")

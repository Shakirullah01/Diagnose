from django.contrib import admin

from .models import Answer, AnswerOption, KidNorm, Question, RCDINorm, SurveySession, SurveyScaleOption, SurveyType


@admin.register(SurveyType)
class SurveyTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("survey_type", "order", "category", "is_active", "text")
    list_filter = ("survey_type", "is_active", "category")
    search_fields = ("text",)


@admin.register(AnswerOption)
class AnswerOptionAdmin(admin.ModelAdmin):
    list_display = ("question", "order", "text", "value")
    search_fields = ("text", "value")


@admin.register(SurveySession)
class SurveySessionAdmin(admin.ModelAdmin):
    list_display = ("survey_type", "user", "started_at", "completed_at", "total_score")
    list_filter = ("survey_type", "completed_at")


@admin.register(SurveyScaleOption)
class SurveyScaleOptionAdmin(admin.ModelAdmin):
    list_display = ("survey_type", "value", "text", "score")
    list_filter = ("survey_type",)


@admin.register(KidNorm)
class KidNormAdmin(admin.ModelAdmin):
    list_display = ("age_months", "category", "normal", "warning", "low")
    list_filter = ("category",)
    ordering = ("age_months", "category")


@admin.register(RCDINorm)
class RCDINormAdmin(admin.ModelAdmin):
    list_display = ("age_months", "sex", "category", "normal", "warning", "low")
    list_filter = ("sex", "category")
    ordering = ("age_months", "sex", "category")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("session", "question", "selected_option", "selected_scale_option", "score", "created_at")

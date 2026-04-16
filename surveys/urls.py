from django.urls import path

from .views import guest_specialist_submit, survey_page, survey_result, survey_start

urlpatterns = [
    path("<slug:slug>/start/", survey_start, name="survey_start"),
    path("<slug:slug>/result/<int:session_id>/", survey_result, name="survey_result"),
    path("<slug:slug>/", survey_page, name="survey_page"),
    path("<slug:slug>/guest/specialist/<int:session_id>/", guest_specialist_submit, name="guest_specialist_submit"),
]


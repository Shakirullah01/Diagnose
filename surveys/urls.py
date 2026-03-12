from django.urls import path

from .views import survey_page

urlpatterns = [
    path("<slug:slug>/", survey_page, name="survey_page"),
]


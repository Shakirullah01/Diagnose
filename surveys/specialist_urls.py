from django.urls import path

from .views import specialist_case_detail, specialist_dashboard

urlpatterns = [
    path("dashboard/", specialist_dashboard, name="specialist_dashboard"),
    path("case/<int:pk>/", specialist_case_detail, name="specialist_case_detail"),
]


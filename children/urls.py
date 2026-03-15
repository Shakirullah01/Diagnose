from django.urls import path

from .views import child_profile_create, child_profile_edit, parent_dashboard

urlpatterns = [
    path("", parent_dashboard, name="parent_dashboard"),
    path("create/", child_profile_create, name="child_profile_create"),
    path("<int:pk>/edit/", child_profile_edit, name="child_profile_edit"),
]

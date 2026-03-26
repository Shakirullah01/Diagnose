from django.contrib import admin
from django.urls import include, path

from surveys.views import home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("accounts/", include("accounts.urls")),
    path("parent/", include("children.urls")),
    path("child/", include("children.urls")),
    path("surveys/", include("surveys.urls")),
    path("specialist/", include("surveys.specialist_urls")),
]


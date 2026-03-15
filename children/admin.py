from django.contrib import admin

from .models import Child, ChildProfile


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "parent", "date_of_birth", "created_at")
    search_fields = ("first_name", "last_name", "parent__email")


@admin.register(ChildProfile)
class ChildProfileAdmin(admin.ModelAdmin):
    list_display = ("child_name", "parent", "birth_date", "filled_by", "created_at")
    list_filter = ("filled_by", "child_health", "where_child_grows")
    search_fields = ("child_name", "parent__email")

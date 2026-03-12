from django.contrib import admin

from .models import Child


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "parent", "date_of_birth", "created_at")
    search_fields = ("first_name", "last_name", "parent__email")

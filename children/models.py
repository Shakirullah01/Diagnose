from django.conf import settings
from django.db import models


class Child(models.Model):
    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="children")
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or f"Child #{self.pk}"


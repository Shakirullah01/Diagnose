from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "name@example.com"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)


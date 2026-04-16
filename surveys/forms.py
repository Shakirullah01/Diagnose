from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .age_utils import calculate_age_months_float


class GuestSurveyStartForm(forms.Form):
    birth_date = forms.DateField(
        label="Дата рождения ребенка",
        required=True,
        widget=forms.DateInput(attrs={"class": "form-control form-control-lg rounded-4", "type": "date"}),
    )
    gender = forms.ChoiceField(
        label="Пол ребенка",
        required=False,
        choices=[("male", "Мужской"), ("female", "Женский")],
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        self.survey_slug = kwargs.pop("survey_slug", "")
        super().__init__(*args, **kwargs)

        # Gender is required only when it is used by the scoring norms.
        if self.survey_slug == "rcdi":
            self.fields["gender"].required = True

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get("birth_date")
        if not birth_date:
            raise ValidationError("Укажите дату рождения.")
        today = timezone.now().date()
        if birth_date > today:
            raise ValidationError("Дата рождения не может быть в будущем.")
        age_months = calculate_age_months_float(birth_date, today=today)
        if age_months > 216:
            raise ValidationError("Указан нереалистичный возраст ребёнка.")
        return birth_date

    def clean_gender(self):
        gender = (self.cleaned_data.get("gender") or "").strip().lower()
        if self.survey_slug == "rcdi":
            if gender not in {"male", "female"}:
                raise ValidationError("Укажите пол ребёнка.")
        if gender not in {"male", "female", ""}:
            raise ValidationError("Укажите пол ребёнка.")
        return gender or None


class GuestContactForm(forms.Form):
    email = forms.EmailField(
        required=False,
        label="Email",
        widget=forms.EmailInput(attrs={"class": "form-control form-control-lg rounded-4", "placeholder": "name@example.com"}),
    )
    phone = forms.CharField(
        required=False,
        label="Телефон",
        widget=forms.TextInput(attrs={"class": "form-control form-control-lg rounded-4", "placeholder": "+7 ..."}),
    )
    max = forms.CharField(
        required=False,
        label="Max (ссылка или ник)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-lg rounded-4", "placeholder": "например: @nick или ссылка"}),
    )
    vk = forms.CharField(
        required=False,
        label="VK (ссылка или ник)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-lg rounded-4", "placeholder": "например: vk.com/... или ник"}),
    )

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return ""
        allowed = set("+0123456789()- ")
        if any(ch not in allowed for ch in phone):
            raise ValidationError("Телефон может содержать только цифры, пробелы и символы +()-")
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) < 10:
            raise ValidationError("Укажите корректный номер телефона.")
        return phone

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email") or ""
        phone = cleaned.get("phone") or ""
        max_ = cleaned.get("max") or ""
        vk_ = cleaned.get("vk") or ""

        if not any([email, phone, max_, vk_]):
            raise ValidationError("Укажите хотя бы один способ связи: email, телефон, VK или Max.")

        # Normalize empty strings
        return {
            "email": email.strip(),
            "phone": phone.strip(),
            "max": max_.strip(),
            "vk": vk_.strip(),
        }


from django import forms
from django.utils import timezone

from .models import ChildProfile


class ChildProfileForm(forms.ModelForm):
    gender = forms.ChoiceField(
        label="Пол",
        required=True,
        choices=[("male", "Мужской"), ("female", "Женский")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    seizures = forms.TypedChoiceField(
        label="Судороги",
        required=True,
        choices=[("true", "да"), ("false", "нет")],
        coerce=lambda x: str(x).lower() in {"true", "1", "yes", "да"},
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = ChildProfile
        fields = [
            "child_name",
            "birth_date",
            "gender",
            "address",
            "phone",
            "filled_by",
            "birth_week",
            "birth_conditions",
            "child_health",
            "seizures",
            "where_child_grows",
            "family_language",
            "children_count",
            "main_caregiver",
            "caregiver_mood",
            "caregiver_values",
            "economic_status",
            "mother_age",
            "father_age",
            "caregiver_age",
            "mother_education",
            "father_education",
            "caregiver_education",
        ]
        widgets = {
            "child_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Имя ребёнка"}),
            "birth_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Адрес"}),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "+7 (___) ___-__-__",
                    "inputmode": "tel",
                    "autocomplete": "tel",
                }
            ),
            "filled_by": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "birth_week": forms.NumberInput(attrs={"class": "form-control", "min": 20, "max": 45, "step": 1}),
            "birth_conditions": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "child_health": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "where_child_grows": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "family_language": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "children_count": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 1}),
            "main_caregiver": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "caregiver_mood": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "caregiver_values": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "economic_status": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "mother_age": forms.NumberInput(attrs={"class": "form-control", "min": 14, "max": 60, "step": 1}),
            "father_age": forms.NumberInput(attrs={"class": "form-control", "min": 14, "max": 60, "step": 1}),
            "caregiver_age": forms.NumberInput(attrs={"class": "form-control", "min": 14, "max": 90, "step": 1}),
            "mother_education": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "father_education": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "caregiver_education": forms.RadioSelect(attrs={"class": "form-check-input"}),
        }

    REQUIRED_MSG = "Это поле обязательно."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["child_name"].required = True
        self.fields["birth_date"].required = True
        self.fields["filled_by"].required = True
        self.fields["filled_by"].error_messages["required"] = self.REQUIRED_MSG
        self.fields["gender"].error_messages["required"] = self.REQUIRED_MSG
        self.fields["birth_week"].initial = self.instance.birth_week or 40

        # Backward-compatible initial values
        existing_gender = (self.instance.gender or "").strip().lower()
        if existing_gender in {"male", "мужской", "м", "boy", "мальчик"}:
            self.fields["gender"].initial = "male"
        elif existing_gender in {"female", "женский", "ж", "girl", "девочка"}:
            self.fields["gender"].initial = "female"

        self.fields["seizures"].initial = bool(self.instance.seizures) if self.instance.pk else False

    def clean_child_name(self):
        name = (self.cleaned_data.get("child_name") or "").strip()
        if not name:
            raise forms.ValidationError("Введите имя ребёнка.")
        return name

    def clean_gender(self):
        gender = (self.cleaned_data.get("gender") or "").strip().lower()
        if gender not in {"male", "female"}:
            raise forms.ValidationError("Укажите пол ребёнка.")
        return "male" if gender == "male" else "female"

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get("birth_date")
        if not birth_date:
            raise forms.ValidationError("Укажите дату рождения.")
        today = timezone.now().date()
        if birth_date > today:
            raise forms.ValidationError("Дата рождения не может быть в будущем.")
        age_months = max(0, (today.year - birth_date.year) * 12 + (today.month - birth_date.month))
        if age_months > 216:
            raise forms.ValidationError("Указан нереалистичный возраст ребёнка.")
        return birth_date

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return phone
        allowed = set("+0123456789()- ")
        if any(ch not in allowed for ch in phone):
            raise forms.ValidationError("Телефон может содержать только цифры, пробелы и символы +()-")
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) < 10:
            raise forms.ValidationError("Укажите корректный номер телефона.")
        return phone

    def _validate_non_negative(self, field_name: str, label: str):
        val = self.cleaned_data.get(field_name)
        if val is not None and val < 0:
            raise forms.ValidationError(f"{label} не может быть отрицательным.")
        return val

    def clean_birth_week(self):
        val = self.cleaned_data.get("birth_week")
        if val is None:
            return val
        if val < 20 or val > 45:
            raise forms.ValidationError("Неделя рождения должна быть в диапазоне 20–45.")
        return val

    def clean_children_count(self):
        return self._validate_non_negative("children_count", "Количество детей в семье")

    def clean_mother_age(self):
        return self._validate_non_negative("mother_age", "Возраст матери")

    def clean_father_age(self):
        return self._validate_non_negative("father_age", "Возраст отца")

    def clean_caregiver_age(self):
        return self._validate_non_negative("caregiver_age", "Возраст ухаживающего")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.gender = "Мужской" if self.cleaned_data.get("gender") == "male" else "Женский"
        instance.seizures = bool(self.cleaned_data.get("seizures"))
        if commit:
            instance.save()
        return instance

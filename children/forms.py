from django import forms

from .models import ChildProfile


class ChildProfileForm(forms.ModelForm):
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
            "gender": forms.TextInput(attrs={"class": "form-control", "placeholder": "Пол"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Адрес"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Телефон"}),
            "filled_by": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "birth_week": forms.NumberInput(attrs={"class": "form-control", "min": 20, "max": 45}),
            "birth_conditions": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "child_health": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "seizures": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "where_child_grows": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "family_language": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "children_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "main_caregiver": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "caregiver_mood": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "caregiver_values": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "economic_status": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "mother_age": forms.NumberInput(attrs={"class": "form-control", "min": 14, "max": 60}),
            "father_age": forms.NumberInput(attrs={"class": "form-control", "min": 14, "max": 60}),
            "caregiver_age": forms.NumberInput(attrs={"class": "form-control", "min": 14, "max": 90}),
            "mother_education": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "father_education": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "caregiver_education": forms.RadioSelect(attrs={"class": "form-check-input"}),
        }

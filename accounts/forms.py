from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import User

UserModel = get_user_model()


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-lg rounded-4",
                "placeholder": "name@example.com",
                "autocomplete": "email",
            }
        ),
    )
    password = forms.CharField(
        label="Пароль",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg rounded-4",
                "placeholder": "Ваш пароль",
                "autocomplete": "current-password",
            }
        ),
    )

    error_messages = {
        "email_not_found": "Аккаунт с таким email не найден.",
        "invalid_password": "Неверный пароль.",
        "invalid_login": "Неверный email или пароль.",
        "inactive": "Аккаунт неактивен. Обратитесь к администратору.",
    }

    def clean(self):
        email = (self.cleaned_data.get("username") or "").strip().lower()
        password = self.cleaned_data.get("password") or ""
        if not email:
            raise ValidationError("Введите email.")
        if not password:
            raise ValidationError("Введите пароль.")

        # В базе могут случайно оказаться дубликаты email с разным регистром
        # (SQLite unique чувствителен к регистру). Поэтому выбираем аккаунт,
        # у которого реальные данные: больше всего привязанных детей.
        matched_qs = UserModel._default_manager.filter(email__iexact=email, is_active=True)
        user = None
        if matched_qs.exists():
            # Небольшие масштабы: считаем детей простым циклом.
            from children.models import ChildProfile

            best = None
            best_children_count = -1
            for u in matched_qs.order_by("id"):
                children_count = ChildProfile.objects.filter(parent_id=u.pk).count()
                if children_count > best_children_count:
                    best_children_count = children_count
                    best = u
            user = best or matched_qs.order_by("id").first()
        if not user:
            raise ValidationError(self.error_messages["email_not_found"])
        if not user.check_password(password):
            raise ValidationError(self.error_messages["invalid_password"])
        if not user.is_active:
            raise ValidationError(self.error_messages["inactive"])

        self.user_cache = user
        self.confirm_login_allowed(user)
        return self.cleaned_data


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-lg rounded-4",
                "placeholder": "name@example.com",
                "autocomplete": "email",
            }
        ),
    )
    password1 = forms.CharField(
        label="Пароль",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg rounded-4",
                "placeholder": "Минимум 8 символов",
                "autocomplete": "new-password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Подтвердите пароль",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg rounded-4",
                "placeholder": "Повторите пароль",
                "autocomplete": "new-password",
            }
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise ValidationError("Email обязателен.")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Пользователь с таким email уже зарегистрирован.")
        return email

    def clean_password1(self):
        password = self.cleaned_data.get("password1")
        if not password:
            raise ValidationError("Пароль обязателен.")
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = (user.email or "").lower()
        if not user.role:
            user.role = User.ROLE_PARENT
        if commit:
            user.save()
        return user


class EmailPasswordResetForm(PasswordResetForm):
    """
    PasswordResetForm на email.

    В Django может не быть метода `clean_email` в базовом классе формы,
    поэтому тут не переопределяем clean_* методы. Регистронезависимый поиск
    делаем в PasswordResetView через `email__iexact`.
    """


from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import LoginView, PasswordResetView as DjangoPasswordResetView
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import EmailAuthenticationForm, EmailPasswordResetForm, RegisterForm


class EmailLoginView(LoginView):
    """Login with email; append ym_goal for Yandex Metrica (handled in base.html)."""

    template_name = "registration/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        url = super().get_success_url()
        if not url:
            url = reverse("parent_dashboard")
        join = "&" if ("?" in url) else "?"
        return f"{url}{join}ym_goal=login_success"


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect(f"{reverse('home')}?ym_goal=registration_complete")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {"form": form})


class PasswordResetView(DjangoPasswordResetView):
    """
    Standard password reset, но выбираем пользователя по email__iexact.
    Так сброс не ломается, если email в базе сохранён с другим регистром.
    """

    form_class = EmailPasswordResetForm

    def get_users(self, email):
        UserModel = get_user_model()
        return UserModel._default_manager.filter(email__iexact=email, is_active=True)


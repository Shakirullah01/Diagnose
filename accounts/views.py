from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import PasswordResetView as DjangoPasswordResetView
from django.shortcuts import redirect, render

from .forms import EmailPasswordResetForm, RegisterForm


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
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


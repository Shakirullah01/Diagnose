from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ChildProfileForm
from .models import ChildProfile


@login_required
def parent_dashboard(request):
    """Мои дети — список анкет и кнопки для прохождения тестов."""
    profiles = ChildProfile.objects.filter(parent=request.user).order_by("-created_at")
    return render(request, "children/parent_dashboard.html", {"profiles": profiles})


@login_required
def child_profile_create(request):
    """Создание анкеты ребёнка."""
    if request.method == "POST":
        form = ChildProfileForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.parent = request.user
            profile.save()
            return redirect("parent_dashboard")
    else:
        form = ChildProfileForm()
    return render(request, "children/child_profile_form.html", {"form": form, "title": "Анкета ребёнка"})


@login_required
def child_profile_edit(request, pk: int):
    """Редактирование анкеты ребёнка."""
    profile = get_object_or_404(ChildProfile, pk=pk, parent=request.user)
    if request.method == "POST":
        form = ChildProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("parent_dashboard")
    else:
        form = ChildProfileForm(instance=profile)
    return render(
        request,
        "children/child_profile_form.html",
        {"form": form, "title": "Редактирование анкеты", "profile": profile},
    )

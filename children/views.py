from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ChildProfileForm
from .models import ChildProfile
from surveys.models import SurveySession


def _parent_only(request):
    if not request.user.is_authenticated:
        return None
    if getattr(request.user, "is_specialist", False):
        return redirect("specialist_dashboard")
    if getattr(request.user, "role", "") != "parent":
        return redirect("home")
    return None


@login_required
def parent_dashboard(request):
    """Мои дети — список анкет и кнопки для прохождения тестов."""
    redirect_response = _parent_only(request)
    if redirect_response:
        return redirect_response
    profiles = ChildProfile.objects.filter(parent=request.user).order_by("-created_at")
    profile_cards = []
    for p in profiles:
        age = p.age_months()
        profile_cards.append(
            {
                "profile": p,
                "age_months": age,
                "show_kdi": age is not None and 2 <= age <= 16,
                "show_rcdi": age is not None and 14 <= age <= 42,
                "show_mchat": age is not None and 16 <= age <= 30,
                "show_ezhs": age is not None and 0 <= age <= 36,
            }
        )

    history_qs = (
        SurveySession.objects.select_related("survey_type", "child_profile")
        .prefetch_related("notes")
        .filter(child_profile__parent=request.user)
        .order_by("-started_at")
    )
    filter_child = (request.GET.get("history_child") or "").strip()
    filter_survey = (request.GET.get("history_survey") or "").strip()
    filter_date = (request.GET.get("history_date") or "").strip()
    if filter_child.isdigit():
        history_qs = history_qs.filter(child_profile_id=int(filter_child))
    if filter_survey:
        history_qs = history_qs.filter(survey_type__slug=filter_survey)
    if filter_date:
        history_qs = history_qs.filter(completed_at__date=filter_date)

    history_rows = []
    for s in history_qs[:100]:
        if s.completed_at is None:
            progress_status = "черновик"
        elif s.consent_to_send and s.status == SurveySession.STATUS_VIEWED:
            progress_status = "просмотрен специалистом"
        elif s.consent_to_send:
            progress_status = "отправлен специалисту"
        else:
            progress_status = "завершен"
        history_rows.append(
            {
                "session": s,
                "progress_status": progress_status,
            }
        )

    return render(
        request,
        "children/parent_dashboard.html",
        {
            "profiles": profiles,
            "profile_cards": profile_cards,
            "history_rows": history_rows,
            "history_filter_child": filter_child,
            "history_filter_survey": filter_survey,
            "history_filter_date": filter_date,
        },
    )


@login_required
def child_profile_create(request):
    """Создание анкеты ребёнка."""
    redirect_response = _parent_only(request)
    if redirect_response:
        return redirect_response
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
    redirect_response = _parent_only(request)
    if redirect_response:
        return redirect_response
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

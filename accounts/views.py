from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required, sampler_required
from accounts.forms import ProfileForm
from accounts.models import User


def login_view(request):
    if request.user.is_authenticated:
        return _redirect_for_role(request.user)

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return _redirect_for_role(form.get_user())
    return render(request, "accounts/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@sampler_required
def profile_view(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@admin_required
def management_dashboard(request):
    return HttpResponse("Management dashboard")


@sampler_required
def mobile_dashboard(request):
    return HttpResponse("Mobile dashboard")


def _redirect_for_role(user):
    if user.role == User.Role.ADMIN:
        return redirect("management-dashboard")
    return redirect("mobile-dashboard")

from django.http import JsonResponse
from django.urls import include, path

from accounts import views as account_views


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health, name="health"),
    path("", include("accounts.urls")),
    path("manage/", account_views.management_dashboard, name="management-dashboard"),
    path("manage/", include("personnel.urls")),
    path("m/", account_views.mobile_dashboard, name="mobile-dashboard"),
]

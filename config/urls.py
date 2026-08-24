from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import include, path

from sampling import management_views, mobile_views


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health, name="health"),
    path("m/", mobile_views.dashboard, name="mobile-dashboard"),
    path("m/", include("sampling.mobile_urls")),
    path("", include("accounts.urls")),
    path("manage/", management_views.dashboard, name="management-dashboard"),
    path("manage/", include("sampling.management_urls")),
    path("manage/", include("personnel.urls")),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView

from accounts import views


app_name = "accounts"

urlpatterns = [
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("img/sampling-hero.png")),
        name="favicon",
    ),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("m/profile/", views.profile_view, name="profile"),
]

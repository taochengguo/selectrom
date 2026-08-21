from django.urls import path

from audit import views


urlpatterns = [
    path("logs/", views.log_list, name="log-list"),
]

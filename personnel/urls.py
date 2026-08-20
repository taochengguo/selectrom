from django.urls import path

from personnel import views


app_name = "personnel"

urlpatterns = [
    path("groups/", views.group_list, name="group-list"),
    path("groups/create/", views.group_create, name="group-create"),
    path("groups/<int:pk>/edit/", views.group_edit, name="group-edit"),
]

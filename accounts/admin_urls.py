from django.urls import path

from sampling import management_views as views


urlpatterns = [
    path("users/", views.user_list, name="user-list"),
    path("users/create/", views.user_create, name="user-create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user-edit"),
    path("users/<int:pk>/toggle-active/", views.user_toggle_active, name="user-toggle-active"),
    path("users/<int:pk>/reset-password/", views.user_reset_password, name="user-reset-password"),
]

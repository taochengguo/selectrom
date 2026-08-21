from django.urls import path

from sampling import mobile_views as views


app_name = "mobile"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tasks/", views.reminders, name="reminders"),
    path("tasks/<int:pk>/", views.task_detail, name="task-detail"),
    path("tasks/<int:pk>/draw/", views.task_draw, name="task-draw"),
    path("tasks/<int:pk>/complete/", views.task_complete, name="task-complete"),
    path("profile/", views.profile, name="profile"),
]

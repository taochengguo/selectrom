from django.urls import include, path

from sampling import management_views as views


app_name = "management"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tasks/", views.task_list, name="task-list"),
    path("tasks/create/", views.task_create, name="task-create"),
    path("tasks/<int:pk>/", views.task_detail, name="task-detail"),
    path("tasks/<int:pk>/edit/", views.task_edit, name="task-edit"),
    path("tasks/<int:pk>/import/", views.task_import, name="task-import"),
    path("tasks/<int:pk>/candidates/add/", views.task_candidate_add, name="task-candidate-add"),
    path("candidates/<int:pk>/delete/", views.task_candidate_delete, name="task-candidate-delete"),
    path("tasks/<int:pk>/ready/", views.task_ready, name="task-ready"),
    path("tasks/<int:pk>/execute/", views.task_execute, name="task-execute"),
    path("tasks/<int:pk>/reassign/", views.task_reassign, name="task-reassign"),
    path(
        "tasks/<int:pk>/authorize-redraw/",
        views.task_authorize_redraw,
        name="task-authorize-redraw",
    ),
    path("tasks/<int:pk>/cancel/", views.task_cancel, name="task-cancel"),
    path("", include("accounts.admin_urls")),
    path("", include("audit.urls")),
]

from django.urls import path

from sampling import mobile_views as views


app_name = "mobile"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tasks/", views.reminders, name="reminders"),
    path("tasks/<int:pk>/", views.task_detail, name="task-detail"),
    path("tasks/<int:pk>/start/", views.task_start, name="task-start"),
    path("tasks/<int:pk>/workflow/", views.task_workflow, name="task-workflow"),
    path("tasks/<int:pk>/draw/", views.task_draw, name="task-draw"),
    path("tasks/<int:pk>/reports/<int:batch_id>/save/", views.task_report_save, name="task-report-save"),
    path("tasks/<int:pk>/reports/<int:batch_id>/photos/", views.task_report_photos, name="task-report-photos"),
    path("tasks/<int:pk>/reports/<int:batch_id>/photos/<int:photo_id>/", views.task_report_photo, name="task-report-photo"),
    path("tasks/<int:pk>/reports/<int:batch_id>/photos/<int:photo_id>/delete/", views.task_report_photo_delete, name="task-report-photo-delete"),
    path("tasks/<int:pk>/reports/<int:batch_id>/check-in/", views.task_report_checkin, name="task-report-checkin"),
    path("tasks/<int:pk>/complete/", views.task_complete, name="task-complete"),
    path("profile/", views.profile, name="profile"),
]

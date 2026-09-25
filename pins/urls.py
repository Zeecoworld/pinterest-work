from django.urls import path

from . import views

app_name = "pins"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("content/", views.content_list, name="content_list"),
    path("content/new/", views.content_create, name="content_create"),
    path("daily-queue/", views.daily_queue, name="daily_queue"),
    path("content/generate-image/", views.generate_ai_image_view, name="generate_ai_image"),
    path("content/<uuid:pk>/", views.content_detail, name="content_detail"),
    path("content/<uuid:pk>/edit/", views.content_edit, name="content_edit"),
    path("content/<uuid:pk>/delete/", views.content_delete, name="content_delete"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("boards/", views.boards_list, name="boards_list"),
    path("categories/", views.categories_list, name="categories_list"),
    path("settings/automation/", views.automation_settings, name="automation_settings"),
    path("settings/pinterest/connect/", views.pinterest_oauth_start, name="pinterest_oauth_start"),
    path("settings/pinterest/callback/", views.pinterest_oauth_callback, name="pinterest_oauth_callback"),
    path("settings/pinterest/disconnect/", views.pinterest_oauth_disconnect, name="pinterest_oauth_disconnect"),
    path("settings/pinterest/sync-boards/", views.pinterest_sync_boards, name="pinterest_sync_boards"),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
]

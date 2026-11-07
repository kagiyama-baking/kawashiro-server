"""Talk（チャット）の URL 設定."""

from django.urls import path

from . import views

app_name = "talk"

urlpatterns = [
    # Talk 設定（チャットで選べる設定とシーン）
    path("settings/", views.TalkSettingsListView.as_view(), name="settings"),
    # チャット履歴 API
    path(
        "sessions/",
        views.ChatSessionListCreateView.as_view(),
        name="session-list-create",
    ),
    path(
        "sessions/<uuid:session_id>/",
        views.ChatSessionDetailView.as_view(),
        name="session-detail",
    ),
    path(
        "sessions/<uuid:session_id>/messages/",
        views.ChatSessionMessageView.as_view(),
        name="session-messages",
    ),
    path(
        "sessions/<uuid:session_id>/messages/<int:msg_id>/",
        views.ChatSessionMessageEditView.as_view(),
        name="session-message-edit",
    ),
    path(
        "sessions/<uuid:session_id>/audio/",
        views.ChatSessionAudioBulkDeleteView.as_view(),
        name="session-audio-bulk",
    ),
    path(
        "sessions/<uuid:session_id>/audio/<int:msg_id>/",
        views.ChatSessionMessageAudioView.as_view(),
        name="session-message-audio",
    ),
]

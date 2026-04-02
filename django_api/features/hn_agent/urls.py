"""HN Agent URLルーティング."""

from django.urls import path

from . import views

app_name = "hn_agent"

urlpatterns = [
    # 一括実行（Watcher → Orchestrator）
    path("run-all/", views.RunAllView.as_view(), name="run-all"),
    # Watcher手動実行
    path("watcher/run/", views.WatcherRunView.as_view(), name="watcher-run"),
    # 調査手動実行
    path("investigate/", views.InvestigateView.as_view(), name="investigate"),
    # スレッド一覧
    path("threads/", views.ThreadListView.as_view(), name="thread-list"),
    # 調査結果一覧
    path(
        "investigations/",
        views.InvestigationListView.as_view(),
        name="investigation-list",
    ),
    # 調査結果詳細
    path(
        "investigations/<int:pk>/",
        views.InvestigationDetailView.as_view(),
        name="investigation-detail",
    ),
]

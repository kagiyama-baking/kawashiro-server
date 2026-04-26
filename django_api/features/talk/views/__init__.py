"""talk アプリのビュー群（モジュール分割）.

外部からは features.talk.views.ViewClass で参照される。urls.py は
変更不要。テストでサービスを patch する際は具体モジュール path
（例: features.talk.views.messages.TalkService）を指定する。
"""

from .audio import ChatSessionAudioBulkDeleteView, ChatSessionMessageAudioView
from .messages import ChatSessionMessageEditView, ChatSessionMessageView
from .sessions import (
    ChatSessionDetailView,
    ChatSessionListCreateView,
    SessionPagination,
)
from .synthesize import ConfigsListView, TalkSynthesizeView, TodayInfoView

__all__ = [
    "ChatSessionAudioBulkDeleteView",
    "ChatSessionDetailView",
    "ChatSessionListCreateView",
    "ChatSessionMessageAudioView",
    "ChatSessionMessageEditView",
    "ChatSessionMessageView",
    "ConfigsListView",
    "SessionPagination",
    "TalkSynthesizeView",
    "TodayInfoView",
]

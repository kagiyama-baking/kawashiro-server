"""talk アプリ用の権限クラス."""

from rest_framework.permissions import BasePermission

from .models import ChatSession


class IsSessionOwner(BasePermission):
    """セッションの所有者のみアクセスを許可する."""

    def has_object_permission(self, request, view, obj) -> bool:
        if isinstance(obj, ChatSession):
            return obj.user_id == request.user.id
        # ChatMessage 等、session 経由の場合
        session = getattr(obj, "session", None)
        if session is not None:
            return session.user_id == request.user.id
        return False

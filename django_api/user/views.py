from rest_framework import authentication, generics, permissions
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import BasePermission
from rest_framework.settings import api_settings
from user.serializers import UserSerializer


class IsSuperUser(BasePermission):
    """Superuserのみアクセスを許可するカスタム権限クラス"""

    def has_permission(self, request, view):
        """ユーザーがSuperuserかどうかをチェック"""
        return request.user and request.user.is_superuser


class CreateUserView(generics.CreateAPIView):
    """システムに新規ユーザーを作成するビュー（Superuserのみ）"""

    # 使用するシリアライザークラスを指定
    serializer_class = UserSerializer
    # トークン認証を要求
    authentication_classes = (authentication.TokenAuthentication,)
    # Superuserのみアクセス可能
    permission_classes = (IsSuperUser,)


class CreateTokenView(ObtainAuthToken):
    """ユーザー用の新しい認証トークンを作成するビュー"""

    # 認証トークンシリアライザーを使用
    serializer_class = AuthTokenSerializer
    # レンダラークラスをAPI設定のデフォルトから取得
    renderer_classes = api_settings.DEFAULT_RENDERER_CLASSES


class ManageUserView(generics.RetrieveUpdateAPIView):
    """認証済みユーザーの情報を管理するビュー"""

    # ユーザーシリアライザーを使用
    serializer_class = UserSerializer
    # トークン認証を要求
    authentication_classes = (authentication.TokenAuthentication,)
    # 認証済みユーザーのみアクセス可能
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        """認証済みユーザー情報を取得して返す"""
        return self.request.user

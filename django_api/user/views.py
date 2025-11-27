from drf_spectacular.utils import extend_schema, extend_schema_view
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


@extend_schema(
    tags=["users"],
    summary="新規ユーザー作成",
    description="Superuserのみが新規ユーザーを作成できます。",
    responses={
        201: UserSerializer,
        401: {"description": "認証エラー"},
        403: {"description": "Superuser権限が必要です"},
        400: {"description": "入力データの検証エラー"},
    },
)
class CreateUserView(generics.CreateAPIView):
    """システムに新規ユーザーを作成するビュー（Superuserのみ）"""

    # 使用するシリアライザークラスを指定
    serializer_class = UserSerializer
    # トークン認証を要求
    authentication_classes = (authentication.TokenAuthentication,)
    # Superuserのみアクセス可能
    permission_classes = (IsSuperUser,)


@extend_schema(
    tags=["auth"],
    summary="認証トークン取得",
    description="ユーザー名とパスワードで認証し、APIアクセス用のトークンを取得します。",
    responses={
        200: {
            "description": "認証成功",
            "content": {
                "application/json": {
                    "example": {
                        "token": "your-authentication-token",
                        "user_id": 1,
                        "email": "user@example.com",
                    }
                }
            },
        },
        400: {"description": "認証失敗 - ユーザー名またはパスワードが正しくありません"},
    },
)
class CreateTokenView(ObtainAuthToken):
    """ユーザー用の新しい認証トークンを作成するビュー"""

    # 認証トークンシリアライザーを使用
    serializer_class = AuthTokenSerializer
    # レンダラークラスをAPI設定のデフォルトから取得
    renderer_classes = api_settings.DEFAULT_RENDERER_CLASSES


@extend_schema_view(
    get=extend_schema(
        tags=["users"],
        summary="ユーザー情報取得",
        description="認証済みユーザーの情報を取得します。",
        responses={200: UserSerializer, 401: {"description": "認証が必要です"}},
    ),
    put=extend_schema(
        tags=["users"],
        summary="ユーザー情報更新",
        description="認証済みユーザーの情報を更新します。",
        responses={
            200: UserSerializer,
            400: {"description": "入力データの検証エラー"},
            401: {"description": "認証が必要です"},
        },
    ),
    patch=extend_schema(
        tags=["users"],
        summary="ユーザー情報部分更新",
        description="認証済みユーザーの情報を部分的に更新します。",
        responses={
            200: UserSerializer,
            400: {"description": "入力データの検証エラー"},
            401: {"description": "認証が必要です"},
        },
    ),
)
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

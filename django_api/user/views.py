from rest_framework import generics
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.settings import api_settings

from user.serializers import UserSerializer


class CreateUserView(generics.CreateAPIView):
    """システムに新規ユーザーを作成するビュー"""
    # 使用するシリアライザークラスを指定
    serializer_class = UserSerializer

class CreateTokenView(ObtainAuthToken):
    """ユーザー用の新しい認証トークンを作成するビュー（Todoへのアクセス制限）"""
    # 認証トークンシリアライザーを使用
    serializer_class = AuthTokenSerializer
    # レンダラークラスをAPI設定のデフォルトから取得
    renderer_classes = api_settings.DEFAULT_RENDERER_CLASSES
from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    """ユーザーオブジェクトのシリアライザー"""

    class Meta:
        model = get_user_model()
        # シリアライズ対象のフィールド
        fields = ("email", "password", "name")
        # パスワードフィールドの追加設定（書き込み専用、最小文字数8文字）
        extra_kwargs = {"password": {"write_only": True, "min_length": 8}}

    def create(self, validated_data):
        """暗号化されたパスワードで新規ユーザーを作成して返す"""
        # create_userメソッドでパスワードを自動的にハッシュ化
        user = get_user_model().objects.create_user(**validated_data)

        return user

    def update(self, instance, validated_data):
        """ユーザー情報を更新し、パスワードを正しく設定して返す"""
        # パスワードフィールドを検証済みデータから取り出す（存在しない場合はNone）
        password = validated_data.pop("password", None)
        # パスワード以外のフィールドを更新
        user = super().update(instance, validated_data)

        # パスワードが指定されている場合は暗号化して保存
        if password:
            user.set_password(password)
            user.save()

        return user


class AuthTokenSerializer(serializers.Serializer):
    """ユーザー認証オブジェクトのシリアライザー"""

    # メールアドレスフィールド
    email = serializers.CharField()
    # パスワードフィールド（入力タイプをpasswordに設定、空白文字をトリムしない）
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False
    )

    def validate(self, attrs):
        """ユーザーの検証と認証を行う"""
        # 入力されたメールアドレスとパスワードを取得
        email = attrs.get("email")
        password = attrs.get("password")

        # Django認証システムを使用してユーザーを認証
        user = authenticate(
            request=self.context.get("request"),
            username=email,  # emailをusernameとして使用
            password=password,
        )
        # 認証に失敗した場合はエラーを発生させる
        if not user:
            msg = "指定された資格情報で認証できませんでした"
            raise serializers.ValidationError(msg, code="authentication")

        # 認証されたユーザーを属性に追加
        attrs["user"] = user
        return attrs

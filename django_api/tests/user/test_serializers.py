"""userアプリのシリアライザーテスト"""

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers

from user.serializers import AuthTokenSerializer, UserSerializer

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.mark.unit
class TestUserSerializer:
    """UserSerializerのテストクラス"""

    def test_serialize_user(self, regular_user):
        """ユーザーオブジェクトが正しくシリアライズされること"""
        serializer = UserSerializer(regular_user)
        data = serializer.data

        assert data["email"] == regular_user.email
        assert data["name"] == regular_user.name
        assert "password" not in data

    def test_create_user_with_valid_data(self):
        """有効なデータでユーザーが作成されること"""
        valid_data = {
            "email": "new@example.com",
            "password": "newpass123",
            "name": "New User",
        }

        serializer = UserSerializer(data=valid_data)
        assert serializer.is_valid()

        user = serializer.save()

        assert user.email == valid_data["email"]
        assert user.name == valid_data["name"]
        assert user.check_password(valid_data["password"])

    def test_create_user_without_email_fails(self):
        """メールアドレスなしでユーザー作成が失敗すること"""
        invalid_data = {"password": "newpass123", "name": "New User"}

        serializer = UserSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert "email" in serializer.errors

    def test_create_user_with_short_password_fails(self):
        """短いパスワードでユーザー作成が失敗すること"""
        invalid_data = {
            "email": "new@example.com",
            "password": "123",
            "name": "New User",
        }

        serializer = UserSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert "password" in serializer.errors

    def test_update_user_password(self, regular_user):
        """ユーザーのパスワードが更新されること"""
        update_data = {"password": "updatedpass123"}

        serializer = UserSerializer(regular_user, data=update_data, partial=True)
        assert serializer.is_valid()

        updated_user = serializer.save()
        assert updated_user.check_password(update_data["password"])

    def test_update_user_name(self, regular_user):
        """ユーザーの名前が更新されること"""
        update_data = {"name": "Updated Name"}

        serializer = UserSerializer(regular_user, data=update_data, partial=True)
        assert serializer.is_valid()

        updated_user = serializer.save()
        assert updated_user.name == update_data["name"]

    def test_password_write_only(self):
        """パスワードフィールドがwrite_onlyであること"""
        serializer = UserSerializer()
        fields = serializer.get_fields()

        assert fields["password"].write_only is True
        # パスワードは部分更新で省略可能なため、requiredはFalseになる
        # （partialフラグがない場合はTrueになる）

    def test_update_user_without_password(self, regular_user):
        """パスワードなしでユーザー情報が更新できること"""
        update_data = {"name": "Updated Name Only"}
        original_password = regular_user.password

        serializer = UserSerializer(regular_user, data=update_data, partial=True)
        assert serializer.is_valid()

        updated_user = serializer.save()
        assert updated_user.name == update_data["name"]
        assert updated_user.password == original_password  # パスワードは変更されない


@pytest.mark.unit
class TestAuthTokenSerializer:
    """AuthTokenSerializerのテストクラス"""

    @patch("user.serializers.authenticate")
    def test_validate_with_valid_credentials(self, mock_authenticate, regular_user):
        """有効な資格情報で認証が成功すること"""
        mock_authenticate.return_value = regular_user

        data = {"email": "user@example.com", "password": "password123"}

        serializer = AuthTokenSerializer(data=data)
        assert serializer.is_valid()

        validated_data = serializer.validated_data
        assert validated_data["user"] == regular_user
        assert validated_data["email"] == "user@example.com"
        assert validated_data["password"] == "password123"

        mock_authenticate.assert_called_once_with(
            request=None, username="user@example.com", password="password123"
        )

    @patch("user.serializers.authenticate")
    def test_validate_with_invalid_credentials(self, mock_authenticate):
        """無効な資格情報で認証が失敗すること"""
        mock_authenticate.return_value = None

        data = {"email": "wrong@example.com", "password": "wrongpass"}

        serializer = AuthTokenSerializer(data=data)

        with pytest.raises(serializers.ValidationError) as excinfo:
            serializer.is_valid(raise_exception=True)

        assert "指定された資格情報で認証できませんでした" in str(excinfo.value)

    @patch("user.serializers.authenticate")
    def test_validate_with_request_context(self, mock_authenticate, regular_user):
        """リクエストコンテキストが認証に渡されること"""
        mock_authenticate.return_value = regular_user
        mock_request = Mock()

        data = {"email": "user@example.com", "password": "password123"}

        serializer = AuthTokenSerializer(data=data, context={"request": mock_request})
        assert serializer.is_valid()

        mock_authenticate.assert_called_once_with(
            request=mock_request, username="user@example.com", password="password123"
        )

    def test_email_field_required(self):
        """メールフィールドが必須であること"""
        data = {"password": "password123"}

        serializer = AuthTokenSerializer(data=data)
        assert not serializer.is_valid()
        assert "email" in serializer.errors

    def test_password_field_required(self):
        """パスワードフィールドが必須であること"""
        data = {"email": "user@example.com"}

        serializer = AuthTokenSerializer(data=data)
        assert not serializer.is_valid()
        assert "password" in serializer.errors

    def test_password_field_style(self):
        """パスワードフィールドのスタイルが正しく設定されていること"""
        serializer = AuthTokenSerializer()
        password_field = serializer.fields["password"]

        assert password_field.style.get("input_type") == "password"
        assert password_field.trim_whitespace is False

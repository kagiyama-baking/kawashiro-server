"""userアプリのシリアライザーテスト"""
import pytest
from django.contrib.auth import get_user_model
from user.serializers import UserSerializer

User = get_user_model()


@pytest.mark.unit
class TestUserSerializer:
    """UserSerializerのテストクラス"""

    def test_serialize_user(self, regular_user):
        """ユーザーオブジェクトが正しくシリアライズされること"""
        serializer = UserSerializer(regular_user)
        data = serializer.data

        assert data['email'] == regular_user.email
        assert data['name'] == regular_user.name
        assert 'password' not in data

    def test_create_user_with_valid_data(self):
        """有効なデータでユーザーが作成されること"""
        valid_data = {
            'email': 'new@example.com',
            'password': 'newpass123',
            'name': 'New User'
        }

        serializer = UserSerializer(data=valid_data)
        assert serializer.is_valid()

        user = serializer.save()

        assert user.email == valid_data['email']
        assert user.name == valid_data['name']
        assert user.check_password(valid_data['password'])

    def test_create_user_without_email_fails(self):
        """メールアドレスなしでユーザー作成が失敗すること"""
        invalid_data = {
            'password': 'newpass123',
            'name': 'New User'
        }

        serializer = UserSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert 'email' in serializer.errors

    def test_create_user_with_short_password_fails(self):
        """短いパスワードでユーザー作成が失敗すること"""
        invalid_data = {
            'email': 'new@example.com',
            'password': '123',
            'name': 'New User'
        }

        serializer = UserSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert 'password' in serializer.errors

    def test_update_user_password(self, regular_user):
        """ユーザーのパスワードが更新されること"""
        update_data = {
            'password': 'updatedpass123'
        }

        serializer = UserSerializer(regular_user, data=update_data, partial=True)
        assert serializer.is_valid()

        updated_user = serializer.save()
        assert updated_user.check_password(update_data['password'])

    def test_update_user_name(self, regular_user):
        """ユーザーの名前が更新されること"""
        update_data = {
            'name': 'Updated Name'
        }

        serializer = UserSerializer(regular_user, data=update_data, partial=True)
        assert serializer.is_valid()

        updated_user = serializer.save()
        assert updated_user.name == update_data['name']

    def test_password_write_only(self):
        """パスワードフィールドがwrite_onlyであること"""
        serializer = UserSerializer()
        fields = serializer.get_fields()

        assert fields['password'].write_only is True
        # パスワードは部分更新で省略可能なため、requiredはFalseになる
        # （partialフラグがない場合はTrueになる）
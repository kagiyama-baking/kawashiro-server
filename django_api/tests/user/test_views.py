"""userアプリのビューテスト"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.mark.api
class TestCreateUserView:
    """CreateUserViewのテストクラス"""

    def test_create_user_with_superuser_permission(self, superuser_client):
        """スーパーユーザーが新規ユーザーを作成できること"""
        payload = {
            "email": "newuser@example.com",
            "password": "newpass123",
            "name": "New User",
        }

        response = superuser_client.post("/user/create/", payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == payload["email"]
        assert response.data["name"] == payload["name"]

        # パスワードが返されないことを確認
        assert "password" not in response.data

        # ユーザーが作成されたことを確認
        user = User.objects.get(email=payload["email"])
        assert user.check_password(payload["password"])

    def test_create_user_without_authentication_fails(self, api_client):
        """認証なしではユーザー作成が失敗すること"""
        payload = {
            "email": "newuser@example.com",
            "password": "newpass123",
            "name": "New User",
        }

        response = api_client.post("/user/create/", payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_user_with_regular_user_permission_fails(self, authenticated_client):
        """一般ユーザーではユーザー作成が失敗すること"""
        payload = {
            "email": "newuser@example.com",
            "password": "newpass123",
            "name": "New User",
        }

        response = authenticated_client.post("/user/create/", payload)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_user_with_invalid_email_fails(self, superuser_client):
        """無効なメールアドレスでユーザー作成が失敗すること"""
        payload = {
            "email": "invalid-email",
            "password": "newpass123",
            "name": "New User",
        }

        response = superuser_client.post("/user/create/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data

    def test_create_user_with_short_password_fails(self, superuser_client):
        """短いパスワードでユーザー作成が失敗すること"""
        payload = {
            "email": "newuser@example.com",
            "password": "123",
            "name": "New User",
        }

        response = superuser_client.post("/user/create/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

    def test_create_user_with_duplicate_email_fails(
        self, superuser_client, regular_user
    ):
        """既存のメールアドレスでユーザー作成が失敗すること"""
        payload = {
            "email": regular_user.email,
            "password": "newpass123",
            "name": "New User",
        }

        response = superuser_client.post("/user/create/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data


@pytest.mark.api
class TestCreateTokenView:
    """CreateTokenViewのテストクラス"""

    def test_create_token_with_valid_credentials(self, api_client, regular_user):
        """正しい認証情報でトークンが取得できること"""
        payload = {
            "username": "test@example.com",  # emailをusernameとして使用
            "password": "testpass123",
        }

        response = api_client.post("/user/token/", payload)

        assert response.status_code == status.HTTP_200_OK
        assert "token" in response.data

        # トークンが正しいユーザーのものか確認
        token = Token.objects.get(key=response.data["token"])
        assert token.user == regular_user

    def test_create_token_with_email_as_username(self, api_client, regular_user):
        """メールアドレスをユーザー名として使用してトークンが取得できること"""
        payload = {"username": regular_user.email, "password": "testpass123"}

        response = api_client.post("/user/token/", payload)

        assert response.status_code == status.HTTP_200_OK
        assert "token" in response.data

    def test_create_token_with_invalid_password_fails(self, api_client, regular_user):
        """誤ったパスワードでトークン取得が失敗すること"""
        payload = {"username": "test@example.com", "password": "wrongpassword"}

        response = api_client.post("/user/token/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_token_with_nonexistent_user_fails(self, api_client):
        """存在しないユーザーでトークン取得が失敗すること"""
        payload = {"username": "nonexistentuser", "password": "somepassword"}

        response = api_client.post("/user/token/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_token_without_credentials_fails(self, api_client):
        """認証情報なしでトークン取得が失敗すること"""
        response = api_client.post("/user/token/", {})

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.api
class TestManageUserView:
    """ManageUserViewのテストクラス"""

    def test_get_user_profile(self, authenticated_client, regular_user):
        """ユーザーが自分のプロフィールを取得できること"""
        response = authenticated_client.get("/user/update/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == regular_user.email
        assert response.data["name"] == regular_user.name
        assert "password" not in response.data

    def test_get_user_profile_without_authentication_fails(self, api_client):
        """認証なしでプロフィール取得が失敗すること"""
        response = api_client.get("/user/update/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_user_profile(self, authenticated_client, regular_user):
        """ユーザーが自分のプロフィールを更新できること"""
        payload = {
            "name": "Updated Name",
            "email": regular_user.email,  # emailは変更しない
            "password": "newpassword123",
        }

        response = authenticated_client.put("/user/update/", payload)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Name"

        # パスワードが更新されたことを確認
        regular_user.refresh_from_db()
        assert regular_user.check_password("newpassword123")

    def test_partial_update_user_profile(self, authenticated_client, regular_user):
        """ユーザーが自分のプロフィールを部分更新できること"""
        payload = {"name": "Partially Updated Name"}

        response = authenticated_client.patch("/user/update/", payload)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Partially Updated Name"
        assert response.data["email"] == regular_user.email

    def test_update_email_to_existing_email_fails(
        self, authenticated_client, superuser
    ):
        """既存のメールアドレスへの変更が失敗すること"""
        payload = {"email": superuser.email}

        response = authenticated_client.patch("/user/update/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data

    def test_update_profile_with_invalid_email_fails(self, authenticated_client):
        """無効なメールアドレスへの更新が失敗すること"""
        payload = {"email": "invalid-email-format"}

        response = authenticated_client.patch("/user/update/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data

    def test_update_profile_with_short_password_fails(self, authenticated_client):
        """短いパスワードでの更新が失敗すること"""
        payload = {"password": "123"}

        response = authenticated_client.patch("/user/update/", payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


class UserManager(BaseUserManager):
    """
    カスタムユーザーマネージャー

    Emailベースの認証を使用するユーザーモデル用のマネージャークラス。
    通常のユーザーとスーパーユーザーの作成メソッドを提供する。
    """

    def create_user(self, email, password=None, **extra_fields):
        """
        新しいユーザーを作成して保存する

        Args:
            email: ユーザーのメールアドレス（必須）
            password: パスワード（オプション）
            **extra_fields: その他のユーザーフィールド

        Returns:
            作成されたUserインスタンス

        Raises:
            ValueError: メールアドレスが指定されていない場合
        """
        if not email:
            raise ValueError('User must have an email address')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password):
        """
        新しいスーパーユーザーを作成して保存する

        管理者権限を持つユーザーを作成する。

        Args:
            email: スーパーユーザーのメールアドレス
            password: パスワード（必須）

        Returns:
            作成されたスーパーユーザーインスタンス
        """
        user = self.create_user(email, password)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)

        return user


class User(AbstractBaseUser, PermissionsMixin):
    """
    カスタムユーザーモデル

    ユーザー名の代わりにメールアドレスを主要な識別子として使用する
    カスタムユーザーモデル。Djangoのデフォルトユーザーモデルを置き換える。

    Attributes:
        email: ユーザーのメールアドレス（一意制約付き）
        name: ユーザーの表示名
        is_active: アカウントの有効/無効状態
        is_staff: 管理画面へのアクセス権限の有無
    """
    email = models.EmailField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # カスタムマネージャーを使用
    objects = UserManager()

    # メールアドレスをユーザー名として使用
    USERNAME_FIELD = 'email'

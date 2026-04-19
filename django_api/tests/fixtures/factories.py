"""テスト用ファクトリ"""

import factory
from django.contrib.auth import get_user_model
from faker import Faker

fake = Faker("ja_JP")  # 日本語のフェイクデータを生成
User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """ユーザーモデルのファクトリ"""

    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Faker("name", locale="ja_JP")
    password = factory.PostGenerationMethodCall("set_password", "defaultpassword123")
    is_active = True
    is_superuser = False

    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for group in extracted:
                self.groups.add(group)

    @classmethod
    def create_batch_with_tokens(cls, size, **kwargs):
        """トークン付きでバッチ作成"""
        from rest_framework.authtoken.models import Token

        users = cls.create_batch(size, **kwargs)
        for user in users:
            Token.objects.create(user=user)
        return users


class SuperUserFactory(UserFactory):
    """スーパーユーザーのファクトリ"""

    email = factory.Sequence(lambda n: f"admin{n}@example.com")
    is_superuser = True
    is_staff = True


class LangfusePromptRefFactory(factory.django.DjangoModelFactory):
    """LangfusePromptRef のファクトリ."""

    class Meta:
        model = "langfuse_integration.LangfusePromptRef"
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"prompt-ref-{n}")
    langfuse_prompt_name = factory.LazyAttribute(lambda o: o.name)
    label = "production"
    fallback_text = "fallback"
    description = ""


class TalkConfigFactory(factory.django.DjangoModelFactory):
    """TalkConfig のファクトリ."""

    class Meta:
        model = "talk.TalkConfig"
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"talk-config-{n}")
    display_name = factory.LazyAttribute(lambda o: o.name)
    area_code = ""
    system_prompt_ref = factory.SubFactory(
        LangfusePromptRefFactory,
        name=factory.LazyAttribute(lambda o: f"{o.factory_parent.name}-system"),
        fallback_text="system prompt fallback",
    )
    user_prompt_ref = factory.SubFactory(
        LangfusePromptRefFactory,
        name=factory.LazyAttribute(lambda o: f"{o.factory_parent.name}-user"),
        fallback_text="user prompt fallback",
    )


class FileUploadFactory:
    """ファイルアップロードテスト用のファクトリ"""

    @staticmethod
    def create_text_file(name="test.txt", content=None):
        """テキストファイルを作成"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        if content is None:
            content = fake.text().encode("utf-8")
        return SimpleUploadedFile(name, content, content_type="text/plain")

    @staticmethod
    def create_pdf_file(name="test.pdf"):
        """PDFファイルを作成（ダミー）"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        # 簡単なPDFヘッダー
        content = b"%PDF-1.4\n%" + fake.text()[:100].encode("utf-8")
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    @staticmethod
    def create_image_file(name="test.png"):
        """画像ファイルを作成（ダミー）"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        # PNGヘッダー（簡略化）
        content = b"\x89PNG\r\n\x1a\n" + fake.binary(length=100)
        return SimpleUploadedFile(name, content, content_type="image/png")

    @staticmethod
    def create_large_file(name="large.bin", size_mb=10):
        """指定サイズの大きなファイルを作成"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        content = fake.binary(length=size_mb * 1024 * 1024)
        return SimpleUploadedFile(
            name, content, content_type="application/octet-stream"
        )

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


class PromptFactory(factory.django.DjangoModelFactory):
    """Prompt（AI設定 → Prompts）のファクトリ（Langfuse のプロンプト名は識別名と同じ）.

    フォールバックテキストは空のまま。本文はテストで Langfuse の代役
    （`langfuse_prompts`）に入れる。
    """

    class Meta:
        model = "llm_config.Prompt"
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"prompt-{n}")
    langfuse_prompt_name = factory.LazyAttribute(lambda o: o.name)
    label = "production"
    description = ""


class TalkSettingFactory(factory.django.DjangoModelFactory):
    """TalkSetting のファクトリ（既定は有効・シーンなし・音声なし）.

    `skills=[...]` を渡すと、そのスキルをシーンとして選んだ設定にする。
    """

    class Meta:
        model = "talk.TalkSetting"
        django_get_or_create = ("name",)
        # 選んだシーンは M2M なので、選んだ後に設定を保存し直さない
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"talk-setting-{n}")
    system_prompt = factory.SubFactory(
        PromptFactory,
        name=factory.LazyAttribute(lambda o: f"{o.factory_parent.name}-system"),
    )

    @factory.post_generation
    def skills(self, create, extracted, **kwargs):
        """`skills` を渡したら、そのスキルを設定のシーンに選ぶ（保存するときだけ）."""
        if create and extracted is not None:
            self.skills.set(extracted)


class AgentSkillFactory(factory.django.DjangoModelFactory):
    """AgentSkill のファクトリ（名前がそのまま本文の Langfuse のプロンプト名。ラベルは staging）."""

    class Meta:
        model = "llm_config.AgentSkill"
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"skill-{n}")
    description = factory.Sequence(lambda n: f"スキル {n} のときに使う")
    label = "staging"


class CompanionConfigFactory(factory.django.DjangoModelFactory):
    """CompanionConfig のファクトリ（既定は無効。有効にするなら is_active=True）.

    `skills=[...]` を渡すと、そのスキルを選んだ設定にする（既定はスキルなし）。
    """

    class Meta:
        model = "companion.CompanionConfig"
        django_get_or_create = ("name",)
        # 選んだスキルは M2M なので、選んだ後に設定を保存し直さない
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"companion-config-{n}")
    system_prompt = factory.SubFactory(
        PromptFactory,
        name=factory.LazyAttribute(lambda o: f"{o.factory_parent.name}-system"),
    )

    @factory.post_generation
    def skills(self, create, extracted, **kwargs):
        """`skills` を渡したら、そのスキルを設定で選ぶ（保存するときだけ）."""
        if create and extracted is not None:
            self.skills.set(extracted)


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

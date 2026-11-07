"""モデルと migration のずれのテスト（makemigrations --check）."""

from io import StringIO

import pytest
from django.core.management import call_command

# プロジェクトのアプリ（第三者アプリの django_celery_beat には、いまのモデルとの既知の差分がある）
PROJECT_APPS = (
    "core",
    "user",
    "msgraph_config",
    "llm_config",
    "langfuse_integration",
    "media",
    "tts",
    "talk",
    "tavily",
    "slack",
    "hn_agent",
    "companion",
)


@pytest.mark.integration
@pytest.mark.django_db
def test_project_apps_have_no_model_changes_without_migration():
    """プロジェクトのアプリのモデルに、migration にしていない変更がない.

    変更があると makemigrations --check は SystemExit で終わる。状態だけの migration
    （モデルの移設・外部キーの向き先の付け替え）の書き漏れもここで分かる。
    """
    out = StringIO()

    call_command("makemigrations", *PROJECT_APPS, check=True, dry_run=True, stdout=out)

    assert "No changes detected" in out.getvalue()

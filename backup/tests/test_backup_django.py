"""backup_django.py のテスト"""

import gzip

import pytest

from scripts.backup_django import (
    DjangoBackupConfig,
    backup_sqlite,
    check_env_vars,
    generate_backup_filename,
)


class TestDjangoBackupConfig:
    """DjangoBackupConfig のテスト"""

    def test_from_env_with_all_required_vars(self, monkeypatch):
        """必須環境変数がすべて設定されている場合、設定が正しく読み込まれること"""
        monkeypatch.setenv("DJANGO_SQLITE_PATH", "/data/db.sqlite3")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/django")

        config = DjangoBackupConfig.from_env()

        assert config.sqlite_path == "/data/db.sqlite3"
        assert config.django_api_url == "http://api.example.com"
        assert config.django_api_token == "token123"
        assert config.onedrive_backup_path == "/backup/django"
        assert config.backup_retention_generations == 7  # デフォルト値

    def test_from_env_with_optional_vars(self, monkeypatch):
        """オプション環境変数も正しく読み込まれること"""
        monkeypatch.setenv("DJANGO_SQLITE_PATH", "/data/db.sqlite3")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/django")
        monkeypatch.setenv("BACKUP_RETENTION_GENERATIONS", "14")

        config = DjangoBackupConfig.from_env()

        assert config.backup_retention_generations == 14

    def test_from_env_with_django_specific_onedrive_path(self, monkeypatch):
        """DJANGO_ONEDRIVE_BACKUP_PATH が優先されること"""
        monkeypatch.setenv("DJANGO_SQLITE_PATH", "/data/db.sqlite3")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/common")
        monkeypatch.setenv("DJANGO_ONEDRIVE_BACKUP_PATH", "/backup/django-specific")

        config = DjangoBackupConfig.from_env()

        assert config.onedrive_backup_path == "/backup/django-specific"

    def test_from_env_missing_required_var_raises_error(self, monkeypatch):
        """必須環境変数が不足している場合、エラーが発生すること"""
        monkeypatch.setenv("DJANGO_SQLITE_PATH", "/data/db.sqlite3")
        # DJANGO_API_URL を設定しない

        with pytest.raises(ValueError, match="必須環境変数.*が設定されていません"):
            DjangoBackupConfig.from_env()


class TestCheckEnvVars:
    """check_env_vars のテスト"""

    def test_check_env_vars_success(self, monkeypatch):
        """すべての環境変数が設定されている場合、正常に終了すること"""
        monkeypatch.setenv("DJANGO_SQLITE_PATH", "/data/db.sqlite3")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/django")

        # エラーが発生しないこと
        config = check_env_vars()
        assert config is not None

    def test_check_env_vars_missing_var(self, monkeypatch):
        """環境変数が不足している場合、エラーが発生すること"""
        monkeypatch.setenv("DJANGO_SQLITE_PATH", "/data/db.sqlite3")

        with pytest.raises(ValueError):
            check_env_vars()


class TestGenerateBackupFilename:
    """generate_backup_filename のテスト"""

    def test_generate_backup_filename(self):
        """バックアップファイル名が正しく生成されること"""
        filename = generate_backup_filename("20250101_120000")
        assert filename == "django_db_20250101_120000.sqlite3.gz"


class TestBackupSqlite:
    """backup_sqlite のテスト"""

    def test_backup_sqlite_success(self, tmp_path):
        """SQLiteバックアップが正常に作成されること"""
        # テスト用のSQLiteファイルを作成
        source_file = tmp_path / "source" / "db.sqlite3"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"SQLite database content")

        backup_file = tmp_path / "backup" / "test_backup.sqlite3.gz"
        backup_file.parent.mkdir(parents=True, exist_ok=True)

        result = backup_sqlite(
            source_path=source_file,
            output_file=backup_file,
        )

        assert result is True
        assert backup_file.exists()

        # gzip で圧縮されていることを確認
        with gzip.open(backup_file, "rb") as f:
            content = f.read()
        assert content == b"SQLite database content"

    def test_backup_sqlite_source_not_found(self, tmp_path):
        """ソースファイルが存在しない場合、エラーが発生すること"""
        source_file = tmp_path / "nonexistent" / "db.sqlite3"
        backup_file = tmp_path / "backup" / "test_backup.sqlite3.gz"
        backup_file.parent.mkdir(parents=True, exist_ok=True)

        with pytest.raises(RuntimeError, match="SQLiteファイルが見つかりません"):
            backup_sqlite(
                source_path=source_file,
                output_file=backup_file,
            )

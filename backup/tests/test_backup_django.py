"""backup_django.py のテスト"""

import gzip
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.backup_django import (
    DjangoBackupConfig,
    backup_sqlite,
    check_env_vars,
    cleanup_local_backups,
    cleanup_old_onedrive_backups,
    delete_old_files,
    generate_backup_filename,
    log_error,
    log_info,
    log_success,
    main,
    upload_to_onedrive,
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


class TestLogFunctions:
    """ログ関数のテスト"""

    def test_log_info(self, capsys):
        """log_info が正しくログを出力すること"""
        log_info("テストメッセージ")
        captured = capsys.readouterr()
        assert "[INFO] テストメッセージ" in captured.out

    def test_log_error(self, capsys):
        """log_error が正しくログを出力すること"""
        log_error("エラーメッセージ")
        captured = capsys.readouterr()
        assert "[ERROR] エラーメッセージ" in captured.err

    def test_log_success(self, capsys):
        """log_success が正しくログを出力すること"""
        log_success("成功メッセージ")
        captured = capsys.readouterr()
        assert "[SUCCESS] 成功メッセージ" in captured.out


class TestUploadToOnedrive:
    """upload_to_onedrive のテスト"""

    def test_upload_success(self, tmp_path):
        """OneDrive へのアップロードが成功すること"""
        test_file = tmp_path / "test_backup.sqlite3.gz"
        test_file.write_bytes(b"test data")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "file123",
            "name": "test_backup.sqlite3.gz",
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_response

            result = upload_to_onedrive(
                file_path=test_file,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
            )

            assert result is True
            mock_post.assert_called_once()

    def test_upload_failure(self, tmp_path):
        """OneDrive へのアップロードが失敗した場合、False を返すこと"""
        test_file = tmp_path / "test_backup.sqlite3.gz"
        test_file.write_bytes(b"test data")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_response

            result = upload_to_onedrive(
                file_path=test_file,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
            )

            assert result is False

    def test_upload_request_exception(self, tmp_path):
        """OneDrive へのアップロードで例外が発生した場合、False を返すこと"""
        test_file = tmp_path / "test_backup.sqlite3.gz"
        test_file.write_bytes(b"test data")

        with patch("requests.post") as mock_post:
            mock_post.side_effect = requests.RequestException("Connection error")

            result = upload_to_onedrive(
                file_path=test_file,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
            )

            assert result is False


class TestCleanupLocalBackups:
    """cleanup_local_backups のテスト"""

    def test_cleanup_removes_all_files(self, tmp_path):
        """バックアップディレクトリ内のすべてのファイルが削除されること"""
        (tmp_path / "backup1.sqlite3.gz").write_bytes(b"data1")
        (tmp_path / "backup2.sqlite3.gz").write_bytes(b"data2")

        deleted_count = cleanup_local_backups(tmp_path)

        assert deleted_count == 2
        assert len(list(tmp_path.iterdir())) == 0

    def test_cleanup_empty_directory(self, tmp_path):
        """空のディレクトリでは何も削除されないこと"""
        deleted_count = cleanup_local_backups(tmp_path)

        assert deleted_count == 0


class TestDeleteOldFiles:
    """delete_old_files のテスト"""

    def test_delete_old_files_when_over_retention(self):
        """保持世代数を超えるファイルが削除されること"""
        files = [
            {"name": "django_db_20250103_120000.sqlite3.gz"},
            {"name": "django_db_20250102_120000.sqlite3.gz"},
            {"name": "django_db_20250101_120000.sqlite3.gz"},
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("requests.delete") as mock_delete:
            mock_delete.return_value = mock_response

            deleted = delete_old_files(
                files=files,
                prefix="django_db_",
                suffix=".sqlite3.gz",
                retention_generations=2,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
            )

            assert deleted == 1
            mock_delete.assert_called_once()

    def test_delete_old_files_when_under_retention(self):
        """保持世代数以内の場合、何も削除されないこと"""
        files = [
            {"name": "django_db_20250102_120000.sqlite3.gz"},
            {"name": "django_db_20250101_120000.sqlite3.gz"},
        ]

        with patch("requests.delete") as mock_delete:
            deleted = delete_old_files(
                files=files,
                prefix="django_db_",
                suffix=".sqlite3.gz",
                retention_generations=3,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
            )

            assert deleted == 0
            mock_delete.assert_not_called()

    def test_delete_old_files_no_matching_files(self):
        """マッチするファイルがない場合、何も削除されないこと"""
        files = [{"name": "other_file.txt"}]

        with patch("requests.delete") as mock_delete:
            deleted = delete_old_files(
                files=files,
                prefix="django_db_",
                suffix=".sqlite3.gz",
                retention_generations=2,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
            )

            assert deleted == 0
            mock_delete.assert_not_called()

    def test_delete_old_files_delete_failure(self):
        """削除に失敗した場合、カウントされないこと"""
        files = [
            {"name": "django_db_20250103_120000.sqlite3.gz"},
            {"name": "django_db_20250102_120000.sqlite3.gz"},
            {"name": "django_db_20250101_120000.sqlite3.gz"},
        ]

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("requests.delete") as mock_delete:
            mock_delete.return_value = mock_response

            deleted = delete_old_files(
                files=files,
                prefix="django_db_",
                suffix=".sqlite3.gz",
                retention_generations=2,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
            )

            assert deleted == 0

    def test_delete_old_files_request_exception(self):
        """削除時に例外が発生した場合、カウントされないこと"""
        files = [
            {"name": "django_db_20250103_120000.sqlite3.gz"},
            {"name": "django_db_20250102_120000.sqlite3.gz"},
            {"name": "django_db_20250101_120000.sqlite3.gz"},
        ]

        with patch("requests.delete") as mock_delete:
            mock_delete.side_effect = requests.RequestException("Connection error")

            deleted = delete_old_files(
                files=files,
                prefix="django_db_",
                suffix=".sqlite3.gz",
                retention_generations=2,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
            )

            assert deleted == 0


class TestCleanupOldOnedriveBackups:
    """cleanup_old_onedrive_backups のテスト"""

    def test_cleanup_old_backups_success(self):
        """古いバックアップが正常に削除されること"""
        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        mock_list_response.json.return_value = {
            "files": [
                {"name": "django_db_20250103_120000.sqlite3.gz"},
                {"name": "django_db_20250102_120000.sqlite3.gz"},
                {"name": "django_db_20250101_120000.sqlite3.gz"},
            ]
        }

        mock_delete_response = MagicMock()
        mock_delete_response.status_code = 200

        with (
            patch("requests.get") as mock_get,
            patch("requests.delete") as mock_delete,
        ):
            mock_get.return_value = mock_list_response
            mock_delete.return_value = mock_delete_response

            result = cleanup_old_onedrive_backups(
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
                retention_generations=2,
            )

            assert result is True
            mock_get.assert_called_once()

    def test_cleanup_old_backups_list_failure(self):
        """ファイル一覧取得に失敗した場合、False を返すこと"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("requests.get") as mock_get:
            mock_get.return_value = mock_response

            result = cleanup_old_onedrive_backups(
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
                retention_generations=2,
            )

            assert result is False

    def test_cleanup_old_backups_request_exception(self):
        """リクエスト例外が発生した場合、False を返すこと"""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Connection error")

            result = cleanup_old_onedrive_backups(
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/django",
                retention_generations=2,
            )

            assert result is False


class TestMain:
    """main 関数のテスト"""

    def test_main_success(self, tmp_path, monkeypatch):
        """バックアップが成功した場合、0を返すこと"""
        # 環境変数を設定
        monkeypatch.setenv("DJANGO_SQLITE_PATH", str(tmp_path / "db.sqlite3"))
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/django")

        # SQLiteファイルを作成
        (tmp_path / "db.sqlite3").write_bytes(b"SQLite database content")

        with (
            patch("scripts.backup_django.Path") as mock_path_class,
            patch("scripts.backup_django.upload_to_onedrive") as mock_upload,
            patch("scripts.backup_django.cleanup_local_backups"),
            patch("scripts.backup_django.cleanup_old_onedrive_backups"),
        ):
            # Pathのモック設定
            mock_backup_dir = MagicMock()
            mock_backup_dir.__truediv__ = MagicMock(
                return_value=tmp_path / "backup.sqlite3.gz"
            )
            mock_path_class.return_value = mock_backup_dir

            # アップロード成功
            mock_upload.return_value = True

            # backup_sqliteが実際のPathを使うようにする
            with patch("scripts.backup_django.backup_sqlite") as mock_backup_sqlite:
                mock_backup_sqlite.return_value = True

                result = main()

                assert result == 0

    def test_main_env_error(self, monkeypatch):
        """環境変数エラーの場合、1を返すこと"""
        # 環境変数をクリア
        monkeypatch.delenv("DJANGO_SQLITE_PATH", raising=False)
        monkeypatch.delenv("DJANGO_API_URL", raising=False)
        monkeypatch.delenv("DJANGO_API_TOKEN", raising=False)
        monkeypatch.delenv("ONEDRIVE_BACKUP_PATH", raising=False)
        monkeypatch.delenv("DJANGO_ONEDRIVE_BACKUP_PATH", raising=False)

        result = main()

        assert result == 1

    def test_main_upload_failure(self, tmp_path, monkeypatch):
        """アップロードに失敗した場合、1を返すこと"""
        monkeypatch.setenv("DJANGO_SQLITE_PATH", str(tmp_path / "db.sqlite3"))
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/django")

        (tmp_path / "db.sqlite3").write_bytes(b"SQLite database content")

        with (
            patch("scripts.backup_django.Path") as mock_path_class,
            patch("scripts.backup_django.upload_to_onedrive") as mock_upload,
            patch("scripts.backup_django.cleanup_local_backups"),
            patch("scripts.backup_django.cleanup_old_onedrive_backups"),
            patch("scripts.backup_django.backup_sqlite") as mock_backup_sqlite,
        ):
            mock_backup_dir = MagicMock()
            mock_backup_dir.__truediv__ = MagicMock(
                return_value=tmp_path / "backup.sqlite3.gz"
            )
            mock_path_class.return_value = mock_backup_dir

            mock_backup_sqlite.return_value = True
            mock_upload.return_value = False

            result = main()

            assert result == 1

    def test_main_backup_runtime_error(self, tmp_path, monkeypatch):
        """バックアップ時にRuntimeErrorが発生した場合、1を返すこと"""
        monkeypatch.setenv("DJANGO_SQLITE_PATH", str(tmp_path / "db.sqlite3"))
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/django")

        with (
            patch("scripts.backup_django.Path") as mock_path_class,
            patch("scripts.backup_django.backup_sqlite") as mock_backup_sqlite,
            patch("scripts.backup_django.cleanup_local_backups"),
        ):
            mock_backup_dir = MagicMock()
            mock_backup_dir.__truediv__ = MagicMock(
                return_value=tmp_path / "backup.sqlite3.gz"
            )
            mock_path_class.return_value = mock_backup_dir

            mock_backup_sqlite.side_effect = RuntimeError("Backup failed")

            result = main()

            assert result == 1

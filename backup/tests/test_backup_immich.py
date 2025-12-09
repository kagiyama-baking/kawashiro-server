"""backup_immich.py のテスト"""

import gzip
from unittest.mock import MagicMock, patch

import pytest

from scripts.backup_immich import (
    BackupConfig,
    backup_database,
    check_env_vars,
    cleanup_local_backups,
    cleanup_old_onedrive_backups,
    delete_old_files,
    generate_backup_filename,
    upload_to_onedrive,
)


class TestBackupConfig:
    """BackupConfig のテスト"""

    def test_from_env_with_all_required_vars(self, monkeypatch):
        """必須環境変数がすべて設定されている場合、設定が正しく読み込まれること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/immich")

        config = BackupConfig.from_env()

        assert config.db_hostname == "localhost"
        assert config.db_username == "testuser"
        assert config.db_password == "testpass"
        assert config.db_database_name == "testdb"
        assert config.django_api_url == "http://api.example.com"
        assert config.django_api_token == "token123"
        assert config.onedrive_backup_path == "/backup/immich"
        assert config.backup_data is False  # デフォルト値
        assert config.backup_retention_generations == 7  # デフォルト値

    def test_from_env_with_optional_vars(self, monkeypatch):
        """オプション環境変数も正しく読み込まれること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/immich")
        monkeypatch.setenv("BACKUP_DATA", "true")
        monkeypatch.setenv("BACKUP_RETENTION_GENERATIONS", "14")

        config = BackupConfig.from_env()

        assert config.backup_data is True
        assert config.backup_retention_generations == 14

    def test_from_env_missing_required_var_raises_error(self, monkeypatch):
        """必須環境変数が不足している場合、エラーが発生すること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        # DB_USERNAME を設定しない

        with pytest.raises(ValueError, match="必須環境変数.*が設定されていません"):
            BackupConfig.from_env()


class TestCheckEnvVars:
    """check_env_vars のテスト"""

    def test_check_env_vars_success(self, monkeypatch):
        """すべての環境変数が設定されている場合、正常に終了すること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/immich")

        # エラーが発生しないこと
        config = check_env_vars()
        assert config is not None

    def test_check_env_vars_missing_var(self, monkeypatch):
        """環境変数が不足している場合、エラーが発生すること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")

        with pytest.raises(ValueError):
            check_env_vars()


class TestGenerateBackupFilename:
    """generate_backup_filename のテスト"""

    def test_generate_db_backup_filename(self):
        """データベースバックアップのファイル名が正しく生成されること"""
        filename = generate_backup_filename("db", "20250101_120000")
        assert filename == "immich_db_20250101_120000.sql.gz"

    def test_generate_data_backup_filename(self):
        """写真データバックアップのファイル名が正しく生成されること"""
        filename = generate_backup_filename("data", "20250101_120000")
        assert filename == "immich_data_20250101_120000.tar.gz"


class TestBackupDatabase:
    """backup_database のテスト"""

    def test_backup_database_success(self, tmp_path, monkeypatch):
        """データベースバックアップが正常に作成されること"""
        backup_file = tmp_path / "test_backup.sql.gz"

        # pg_dump コマンドをモック
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"CREATE TABLE test;"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            # gzip 圧縮をシミュレート
            with gzip.open(backup_file, "wt") as f:
                f.write("CREATE TABLE test;")

            result = backup_database(
                hostname="localhost",
                username="testuser",
                password="testpass",
                database="testdb",
                output_file=backup_file,
            )

            assert result is True
            mock_run.assert_called_once()

    def test_backup_database_failure(self, tmp_path):
        """pg_dump が失敗した場合、エラーが発生すること"""
        backup_file = tmp_path / "test_backup.sql.gz"

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"connection refused"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            with pytest.raises(RuntimeError, match="データベースバックアップに失敗"):
                backup_database(
                    hostname="localhost",
                    username="testuser",
                    password="testpass",
                    database="testdb",
                    output_file=backup_file,
                )


class TestUploadToOnedrive:
    """upload_to_onedrive のテスト"""

    def test_upload_success(self, tmp_path):
        """OneDrive へのアップロードが成功すること"""
        test_file = tmp_path / "test_backup.sql.gz"
        test_file.write_bytes(b"test data")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "file123",
            "name": "test_backup.sql.gz",
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_response

            result = upload_to_onedrive(
                file_path=test_file,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/immich",
            )

            assert result is True
            mock_post.assert_called_once()

    def test_upload_failure(self, tmp_path):
        """OneDrive へのアップロードが失敗した場合、False を返すこと"""
        test_file = tmp_path / "test_backup.sql.gz"
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
                folder_path="/backup/immich",
            )

            assert result is False


class TestCleanupLocalBackups:
    """cleanup_local_backups のテスト"""

    def test_cleanup_removes_all_files(self, tmp_path):
        """バックアップディレクトリ内のすべてのファイルが削除されること"""
        # テストファイルを作成
        (tmp_path / "backup1.sql.gz").write_bytes(b"data1")
        (tmp_path / "backup2.sql.gz").write_bytes(b"data2")
        (tmp_path / "backup3.tar.gz").write_bytes(b"data3")

        deleted_count = cleanup_local_backups(tmp_path)

        assert deleted_count == 3
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
            {"name": "immich_db_20250103_120000.sql.gz"},
            {"name": "immich_db_20250102_120000.sql.gz"},
            {"name": "immich_db_20250101_120000.sql.gz"},
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("requests.delete") as mock_delete:
            mock_delete.return_value = mock_response

            deleted = delete_old_files(
                files=files,
                prefix="immich_db_",
                suffix=".sql.gz",
                retention_generations=2,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/immich",
            )

            assert deleted == 1
            mock_delete.assert_called_once()

    def test_delete_old_files_when_under_retention(self):
        """保持世代数以内の場合、何も削除されないこと"""
        files = [
            {"name": "immich_db_20250102_120000.sql.gz"},
            {"name": "immich_db_20250101_120000.sql.gz"},
        ]

        with patch("requests.delete") as mock_delete:
            deleted = delete_old_files(
                files=files,
                prefix="immich_db_",
                suffix=".sql.gz",
                retention_generations=3,
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/immich",
            )

            assert deleted == 0
            mock_delete.assert_not_called()


class TestCleanupOldOnedriveBackups:
    """cleanup_old_onedrive_backups のテスト"""

    def test_cleanup_old_backups_success(self):
        """古いバックアップが正常に削除されること"""
        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        mock_list_response.json.return_value = {
            "files": [
                {"name": "immich_db_20250103_120000.sql.gz"},
                {"name": "immich_db_20250102_120000.sql.gz"},
                {"name": "immich_db_20250101_120000.sql.gz"},
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
                folder_path="/backup/immich",
                retention_generations=2,
                backup_data=False,
            )

            assert result is True
            mock_get.assert_called_once()

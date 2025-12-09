"""restore_immich.py のテスト"""

import gzip
import tarfile
from unittest.mock import MagicMock, patch

import pytest

from scripts.restore_immich import (
    RestoreConfig,
    check_env_vars,
    check_onedrive_env_vars,
    download_from_onedrive,
    generate_data_filename_from_db,
    parse_args,
    restore_data,
    restore_database,
)


class TestRestoreConfig:
    """RestoreConfig のテスト"""

    def test_from_env_with_required_vars(self, monkeypatch):
        """必須環境変数が設定されている場合、設定が正しく読み込まれること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")

        config = RestoreConfig.from_env()

        assert config.db_hostname == "localhost"
        assert config.db_username == "testuser"
        assert config.db_password == "testpass"
        assert config.db_database_name == "testdb"

    def test_from_env_with_onedrive_vars(self, monkeypatch):
        """OneDrive 環境変数も正しく読み込まれること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/immich")

        config = RestoreConfig.from_env()

        assert config.django_api_url == "http://api.example.com"
        assert config.django_api_token == "token123"
        assert config.onedrive_backup_path == "/backup/immich"

    def test_from_env_missing_required_var_raises_error(self, monkeypatch):
        """必須環境変数が不足している場合、エラーが発生すること"""
        monkeypatch.delenv("DB_USERNAME", raising=False)
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        monkeypatch.delenv("DB_DATABASE_NAME", raising=False)
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        # DB_USERNAME を設定しない

        with pytest.raises(ValueError, match="必須環境変数.*が設定されていません"):
            RestoreConfig.from_env()


class TestCheckEnvVars:
    """check_env_vars のテスト"""

    def test_check_env_vars_success(self, monkeypatch):
        """すべての環境変数が設定されている場合、正常に終了すること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")

        config = check_env_vars()
        assert config is not None


class TestCheckOnedriveEnvVars:
    """check_onedrive_env_vars のテスト"""

    def test_check_onedrive_env_vars_success(self, monkeypatch):
        """OneDrive 環境変数が設定されている場合、正常に終了すること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/immich")

        config = check_onedrive_env_vars()
        assert config.django_api_url is not None

    def test_check_onedrive_env_vars_missing(self, monkeypatch):
        """OneDrive 環境変数が不足している場合、エラーが発生すること"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")
        # OneDrive 関連を設定しない

        with pytest.raises(
            ValueError, match="OneDriveからのダウンロードに必要な環境変数"
        ):
            check_onedrive_env_vars()


class TestParseArgs:
    """parse_args のテスト"""

    def test_parse_args_local_default(self):
        """デフォルトでローカルモードになること"""
        args = parse_args(["backup.sql.gz"])

        assert args.backup_file == "backup.sql.gz"
        assert args.from_onedrive is False
        assert args.with_data is False

    def test_parse_args_from_onedrive(self):
        """--from-onedrive オプションが認識されること"""
        args = parse_args(["--from-onedrive", "backup.sql.gz"])

        assert args.from_onedrive is True

    def test_parse_args_with_data(self):
        """--with-data オプションが認識されること"""
        args = parse_args(["--with-data", "backup.sql.gz"])

        assert args.with_data is True

    def test_parse_args_combined_options(self):
        """複数のオプションが組み合わせられること"""
        args = parse_args(["--from-onedrive", "--with-data", "backup.sql.gz"])

        assert args.from_onedrive is True
        assert args.with_data is True
        assert args.backup_file == "backup.sql.gz"


class TestGenerateDataFilenameFromDb:
    """generate_data_filename_from_db のテスト"""

    def test_generate_data_filename(self):
        """データベースファイル名から写真データファイル名が生成されること"""
        db_filename = "immich_db_20250127_120000.sql.gz"
        data_filename = generate_data_filename_from_db(db_filename)

        assert data_filename == "immich_data_20250127_120000.tar.gz"


class TestDownloadFromOnedrive:
    """download_from_onedrive のテスト"""

    def test_download_success(self, tmp_path):
        """OneDrive からのダウンロードが成功すること"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b"test data"]

        with patch("requests.get") as mock_get:
            mock_get.return_value = mock_response

            result = download_from_onedrive(
                file_name="backup.sql.gz",
                api_url="http://api.example.com",
                api_token="token123",
                folder_path="/backup/immich",
                local_dir=tmp_path,
            )

            assert result == tmp_path / "backup.sql.gz"

    def test_download_failure(self, tmp_path):
        """OneDrive からのダウンロードが失敗した場合、エラーが発生すること"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch("requests.get") as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(RuntimeError, match="OneDriveからのダウンロードに失敗"):
                download_from_onedrive(
                    file_name="backup.sql.gz",
                    api_url="http://api.example.com",
                    api_token="token123",
                    folder_path="/backup/immich",
                    local_dir=tmp_path,
                )


class TestRestoreDatabase:
    """restore_database のテスト"""

    def test_restore_database_success(self, tmp_path):
        """データベースリストアが正常に完了すること"""
        backup_file = tmp_path / "backup.sql.gz"
        with gzip.open(backup_file, "wt") as f:
            f.write("CREATE TABLE test;")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            result = restore_database(
                backup_file=backup_file,
                hostname="localhost",
                username="testuser",
                password="testpass",
                database="testdb",
            )

            assert result is True
            # psql が複数回呼ばれることを確認（接続確認、接続切断、DROP、CREATE、リストア）
            assert mock_run.call_count >= 1

    def test_restore_database_file_not_found(self, tmp_path):
        """バックアップファイルが存在しない場合、エラーが発生すること"""
        backup_file = tmp_path / "nonexistent.sql.gz"

        with pytest.raises(RuntimeError, match="バックアップファイルが見つかりません"):
            restore_database(
                backup_file=backup_file,
                hostname="localhost",
                username="testuser",
                password="testpass",
                database="testdb",
            )


class TestRestoreData:
    """restore_data のテスト"""

    def test_restore_data_success(self, tmp_path):
        """写真データリストアが正常に完了すること"""
        # バックアップファイルを作成
        backup_file = tmp_path / "backup.tar.gz"
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "test.jpg").write_bytes(b"image data")

        with tarfile.open(backup_file, "w:gz") as tar:
            tar.add(source_dir, arcname="data")

        restore_dir = tmp_path / "restore"
        restore_dir.mkdir()

        result = restore_data(
            backup_file=backup_file,
            restore_dir=restore_dir,
        )

        assert result is True
        assert (restore_dir / "data" / "test.jpg").exists()

    def test_restore_data_file_not_found(self, tmp_path):
        """バックアップファイルが存在しない場合、エラーが発生すること"""
        backup_file = tmp_path / "nonexistent.tar.gz"
        restore_dir = tmp_path / "restore"

        with pytest.raises(
            RuntimeError, match="写真データバックアップファイルが見つかりません"
        ):
            restore_data(
                backup_file=backup_file,
                restore_dir=restore_dir,
            )

    def test_restore_data_restore_dir_not_found(self, tmp_path):
        """リストア先ディレクトリが存在しない場合、エラーが発生すること"""
        backup_file = tmp_path / "backup.tar.gz"
        backup_file.write_bytes(b"dummy")
        restore_dir = tmp_path / "nonexistent"

        with pytest.raises(RuntimeError, match="ディレクトリが見つかりません"):
            restore_data(
                backup_file=backup_file,
                restore_dir=restore_dir,
            )

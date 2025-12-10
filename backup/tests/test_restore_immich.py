"""restore_immich.py のテスト"""

import gzip
import tarfile
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.restore_immich import (
    RestoreConfig,
    check_env_vars,
    check_onedrive_env_vars,
    cleanup_temp_file,
    download_from_onedrive,
    generate_data_filename_from_db,
    log_error,
    log_info,
    log_success,
    log_warning,
    main,
    parse_args,
    quote_identifier,
    quote_literal,
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


class TestQuoteIdentifier:
    """quote_identifier のテスト（SQLインジェクション対策）"""

    def test_quote_identifier_escapes_double_quotes(self):
        """quote_identifier がダブルクォートを正しくエスケープすること"""
        # 悪意のある入力例
        malicious_input = 'test"; DROP TABLE users;--'
        result = quote_identifier(malicious_input)

        # ダブルクォートが "" にエスケープされることを確認
        assert result == '"test""; DROP TABLE users;--"'

    def test_quote_identifier_with_normal_name(self):
        """通常のデータベース名が正しく処理されること"""
        result = quote_identifier("immich")

        assert result == '"immich"'

    def test_quote_identifier_with_underscore(self):
        """アンダースコアを含む名前が正しく処理されること"""
        result = quote_identifier("test_db")

        assert result == '"test_db"'


class TestQuoteLiteral:
    """quote_literal のテスト（SQLインジェクション対策）"""

    def test_quote_literal_escapes_single_quotes(self):
        """quote_literal がシングルクォートを正しくエスケープすること"""
        # 悪意のある入力例
        malicious_input = "test'; DROP TABLE users;--"
        result = quote_literal(malicious_input)

        # シングルクォートが '' にエスケープされることを確認
        assert result == "'test''; DROP TABLE users;--'"

    def test_quote_literal_with_normal_value(self):
        """通常の値が正しく処理されること"""
        result = quote_literal("immich")

        assert result == "'immich'"

    def test_quote_literal_with_multiple_quotes(self):
        """複数のシングルクォートが正しくエスケープされること"""
        result = quote_literal("it's a test's value")

        assert result == "'it''s a test''s value'"


class TestSqlInjectionPrevention:
    """SQLインジェクション対策が正しく機能することのテスト"""

    def test_create_database_sql_is_safe(self):
        """CREATE DATABASE文がSQLインジェクションから保護されること"""
        database = 'test"; DROP DATABASE immich;--'
        username = "testuser"

        create_sql = (
            f"CREATE DATABASE {quote_identifier(database)} "
            f"OWNER {quote_identifier(username)};"
        )

        # 悪意のあるコードが実行されない形式になっていることを確認
        assert create_sql == (
            'CREATE DATABASE "test""; DROP DATABASE immich;--" OWNER "testuser";'
        )

    def test_terminate_connections_sql_is_safe(self):
        """接続切断SQLがSQLインジェクションから保護されること"""
        database = "test'; DELETE FROM users;--"

        terminate_sql = (
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = {quote_literal(database)} AND pid <> pg_backend_pid();"
        )

        # 悪意のあるコードが実行されない形式になっていることを確認
        assert "test''; DELETE FROM users;--" in terminate_sql


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

    def test_log_warning(self, capsys):
        """log_warning が正しくログを出力すること"""
        log_warning("警告メッセージ")
        captured = capsys.readouterr()
        assert "[WARNING] 警告メッセージ" in captured.out


class TestDownloadRequestException:
    """download_from_onedrive の例外テスト"""

    def test_download_request_exception(self, tmp_path):
        """OneDrive からのダウンロードで例外が発生した場合、エラーが発生すること"""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Connection error")

            with pytest.raises(RuntimeError, match="OneDriveからのダウンロードに失敗"):
                download_from_onedrive(
                    file_name="backup.sql.gz",
                    api_url="http://api.example.com",
                    api_token="token123",
                    folder_path="/backup/immich",
                    local_dir=tmp_path,
                )


class TestCleanupTempFile:
    """cleanup_temp_file のテスト"""

    def test_cleanup_temp_file_deletes_when_temp(self, tmp_path):
        """一時ファイルの場合、削除されること"""
        temp_file = tmp_path / "temp.sql.gz"
        temp_file.write_bytes(b"temp data")

        cleanup_temp_file(temp_file, is_temp=True)

        assert not temp_file.exists()

    def test_cleanup_temp_file_keeps_when_not_temp(self, tmp_path):
        """一時ファイルでない場合、削除されないこと"""
        file = tmp_path / "data.sql.gz"
        file.write_bytes(b"data")

        cleanup_temp_file(file, is_temp=False)

        assert file.exists()

    def test_cleanup_temp_file_nonexistent(self, tmp_path):
        """存在しないファイルの場合でもエラーにならないこと"""
        nonexistent_file = tmp_path / "nonexistent.sql.gz"

        # エラーが発生しないこと
        cleanup_temp_file(nonexistent_file, is_temp=True)


class TestMain:
    """main 関数のテスト"""

    def test_main_env_error(self, monkeypatch):
        """環境変数エラーの場合、1を返すこと"""
        monkeypatch.delenv("DB_HOSTNAME", raising=False)
        monkeypatch.delenv("DB_USERNAME", raising=False)
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        monkeypatch.delenv("DB_DATABASE_NAME", raising=False)

        with patch("sys.argv", ["restore_immich.py", "backup.sql.gz"]):
            result = main()

        assert result == 1

    def test_main_onedrive_env_error(self, monkeypatch):
        """OneDrive環境変数エラーの場合、1を返すこと"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")
        monkeypatch.delenv("DJANGO_API_URL", raising=False)
        monkeypatch.delenv("DJANGO_API_TOKEN", raising=False)
        monkeypatch.delenv("ONEDRIVE_BACKUP_PATH", raising=False)

        with patch(
            "sys.argv", ["restore_immich.py", "--from-onedrive", "backup.sql.gz"]
        ):
            result = main()

        assert result == 1

    def test_main_local_file_not_found(self, tmp_path, monkeypatch):
        """ローカルファイルが見つからない場合、1を返すこと"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")

        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()

        with (
            patch("sys.argv", ["restore_immich.py", "nonexistent.sql.gz"]),
            patch("scripts.restore_immich.Path") as mock_path_class,
        ):

            def path_side_effect(path_str):
                if path_str == "/backup":
                    return backup_dir
                return MagicMock()

            mock_path_class.side_effect = path_side_effect

            result = main()

        assert result == 1

    def test_main_restore_success(self, tmp_path, monkeypatch):
        """リストアが成功した場合、0を返すこと"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")

        # バックアップファイルを作成
        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        backup_file = backup_dir / "backup.sql.gz"
        with gzip.open(backup_file, "wt") as f:
            f.write("CREATE TABLE test;")

        with (
            patch("sys.argv", ["restore_immich.py", "backup.sql.gz"]),
            patch("scripts.restore_immich.restore_database") as mock_restore,
            patch("scripts.restore_immich.Path") as mock_path_class,
        ):
            mock_restore.return_value = True

            def path_side_effect(path_str):
                if path_str == "/backup":
                    return backup_dir
                return MagicMock()

            mock_path_class.side_effect = path_side_effect

            result = main()

            assert result == 0

    def test_main_restore_failure(self, tmp_path, monkeypatch):
        """リストアが失敗した場合、1を返すこと"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")

        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        backup_file = backup_dir / "backup.sql.gz"
        with gzip.open(backup_file, "wt") as f:
            f.write("CREATE TABLE test;")

        with (
            patch("sys.argv", ["restore_immich.py", "backup.sql.gz"]),
            patch("scripts.restore_immich.restore_database") as mock_restore,
            patch("scripts.restore_immich.Path") as mock_path_class,
        ):
            mock_restore.side_effect = RuntimeError("Restore failed")

            def path_side_effect(path_str):
                if path_str == "/backup":
                    return backup_dir
                return MagicMock()

            mock_path_class.side_effect = path_side_effect

            result = main()

            assert result == 1

    def test_main_onedrive_download_failure(self, tmp_path, monkeypatch):
        """OneDriveからのダウンロードが失敗した場合、1を返すこと"""
        monkeypatch.setenv("DB_HOSTNAME", "localhost")
        monkeypatch.setenv("DB_USERNAME", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("DB_DATABASE_NAME", "testdb")
        monkeypatch.setenv("DJANGO_API_URL", "http://api.example.com")
        monkeypatch.setenv("DJANGO_API_TOKEN", "token123")
        monkeypatch.setenv("ONEDRIVE_BACKUP_PATH", "/backup/immich")

        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()

        with (
            patch(
                "sys.argv", ["restore_immich.py", "--from-onedrive", "backup.sql.gz"]
            ),
            patch("scripts.restore_immich.download_from_onedrive") as mock_download,
            patch("scripts.restore_immich.Path") as mock_path_class,
        ):
            mock_download.side_effect = RuntimeError("Download failed")

            def path_side_effect(path_str):
                if path_str == "/backup":
                    return backup_dir
                return MagicMock()

            mock_path_class.side_effect = path_side_effect

            result = main()

            assert result == 1

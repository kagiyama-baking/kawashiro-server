"""backup_all.py のテスト"""

from unittest.mock import patch

from scripts.backup_all import (
    log_error,
    log_info,
    log_success,
    main,
    parse_args,
    run_backup,
    run_django_backup,
    run_immich_backup,
)


class TestRunImmichBackup:
    """run_immich_backup のテスト"""

    def test_run_immich_backup_success(self):
        """Immichバックアップが成功した場合、0を返すこと"""
        with patch("scripts.backup_all.backup_immich_main") as mock_main:
            mock_main.return_value = 0

            result = run_immich_backup()

            assert result == 0
            mock_main.assert_called_once()

    def test_run_immich_backup_failure(self):
        """Immichバックアップが失敗した場合、1を返すこと"""
        with patch("scripts.backup_all.backup_immich_main") as mock_main:
            mock_main.return_value = 1

            result = run_immich_backup()

            assert result == 1

    def test_run_immich_backup_exception(self):
        """Immichバックアップで例外が発生した場合、1を返すこと"""
        with patch("scripts.backup_all.backup_immich_main") as mock_main:
            mock_main.side_effect = Exception("Test error")

            result = run_immich_backup()

            assert result == 1


class TestRunDjangoBackup:
    """run_django_backup のテスト"""

    def test_run_django_backup_success(self):
        """Djangoバックアップが成功した場合、0を返すこと"""
        with patch("scripts.backup_all.backup_django_main") as mock_main:
            mock_main.return_value = 0

            result = run_django_backup()

            assert result == 0
            mock_main.assert_called_once()

    def test_run_django_backup_failure(self):
        """Djangoバックアップが失敗した場合、1を返すこと"""
        with patch("scripts.backup_all.backup_django_main") as mock_main:
            mock_main.return_value = 1

            result = run_django_backup()

            assert result == 1

    def test_run_django_backup_exception(self):
        """Djangoバックアップで例外が発生した場合、1を返すこと"""
        with patch("scripts.backup_all.backup_django_main") as mock_main:
            mock_main.side_effect = Exception("Test error")

            result = run_django_backup()

            assert result == 1


class TestRunBackup:
    """run_backup のテスト"""

    def test_run_backup_all_success(self):
        """両方のバックアップが成功した場合、0を返すこと"""
        with (
            patch("scripts.backup_all.run_immich_backup") as mock_immich,
            patch("scripts.backup_all.run_django_backup") as mock_django,
        ):
            mock_immich.return_value = 0
            mock_django.return_value = 0

            result = run_backup(immich=True, django=True)

            assert result == 0
            mock_immich.assert_called_once()
            mock_django.assert_called_once()

    def test_run_backup_immich_only(self):
        """Immichのみバックアップする場合"""
        with (
            patch("scripts.backup_all.run_immich_backup") as mock_immich,
            patch("scripts.backup_all.run_django_backup") as mock_django,
        ):
            mock_immich.return_value = 0

            result = run_backup(immich=True, django=False)

            assert result == 0
            mock_immich.assert_called_once()
            mock_django.assert_not_called()

    def test_run_backup_django_only(self):
        """Djangoのみバックアップする場合"""
        with (
            patch("scripts.backup_all.run_immich_backup") as mock_immich,
            patch("scripts.backup_all.run_django_backup") as mock_django,
        ):
            mock_django.return_value = 0

            result = run_backup(immich=False, django=True)

            assert result == 0
            mock_immich.assert_not_called()
            mock_django.assert_called_once()

    def test_run_backup_immich_fails(self):
        """Immichバックアップが失敗した場合、1を返すこと"""
        with (
            patch("scripts.backup_all.run_immich_backup") as mock_immich,
            patch("scripts.backup_all.run_django_backup") as mock_django,
        ):
            mock_immich.return_value = 1
            mock_django.return_value = 0

            result = run_backup(immich=True, django=True)

            assert result == 1
            # Djangoバックアップも実行されること（途中で止まらない）
            mock_django.assert_called_once()

    def test_run_backup_django_fails(self):
        """Djangoバックアップが失敗した場合、1を返すこと"""
        with (
            patch("scripts.backup_all.run_immich_backup") as mock_immich,
            patch("scripts.backup_all.run_django_backup") as mock_django,
        ):
            mock_immich.return_value = 0
            mock_django.return_value = 1

            result = run_backup(immich=True, django=True)

            assert result == 1

    def test_run_backup_no_target(self):
        """バックアップ対象がない場合、0を返すこと"""
        with (
            patch("scripts.backup_all.run_immich_backup") as mock_immich,
            patch("scripts.backup_all.run_django_backup") as mock_django,
        ):
            result = run_backup(immich=False, django=False)

            assert result == 0
            mock_immich.assert_not_called()
            mock_django.assert_not_called()


class TestParseArgs:
    """parse_args のテスト"""

    def test_parse_args_default(self):
        """デフォルトでは両方のバックアップが対象になること"""
        with patch("sys.argv", ["backup_all.py"]):
            args = parse_args()

            assert args.immich_only is False
            assert args.django_only is False

    def test_parse_args_immich_only(self):
        """--immich-only オプションが認識されること"""
        with patch("sys.argv", ["backup_all.py", "--immich-only"]):
            args = parse_args()

            assert args.immich_only is True
            assert args.django_only is False

    def test_parse_args_django_only(self):
        """--django-only オプションが認識されること"""
        with patch("sys.argv", ["backup_all.py", "--django-only"]):
            args = parse_args()

            assert args.immich_only is False
            assert args.django_only is True


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


class TestMain:
    """main 関数のテスト"""

    def test_main_all_success(self):
        """全バックアップが成功した場合、0を返すこと"""
        with (
            patch("sys.argv", ["backup_all.py"]),
            patch("scripts.backup_all.run_backup") as mock_run_backup,
        ):
            mock_run_backup.return_value = 0

            result = main()

            assert result == 0
            mock_run_backup.assert_called_once_with(immich=True, django=True)

    def test_main_immich_only(self):
        """--immich-only オプションで Immich のみバックアップされること"""
        with (
            patch("sys.argv", ["backup_all.py", "--immich-only"]),
            patch("scripts.backup_all.run_backup") as mock_run_backup,
        ):
            mock_run_backup.return_value = 0

            result = main()

            assert result == 0
            mock_run_backup.assert_called_once_with(immich=True, django=False)

    def test_main_django_only(self):
        """--django-only オプションで Django のみバックアップされること"""
        with (
            patch("sys.argv", ["backup_all.py", "--django-only"]),
            patch("scripts.backup_all.run_backup") as mock_run_backup,
        ):
            mock_run_backup.return_value = 0

            result = main()

            assert result == 0
            mock_run_backup.assert_called_once_with(immich=False, django=True)

    def test_main_failure(self):
        """バックアップが失敗した場合、1を返すこと"""
        with (
            patch("sys.argv", ["backup_all.py"]),
            patch("scripts.backup_all.run_backup") as mock_run_backup,
        ):
            mock_run_backup.return_value = 1

            result = main()

            assert result == 1

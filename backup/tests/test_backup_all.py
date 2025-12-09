"""backup_all.py のテスト"""

from unittest.mock import patch

from scripts.backup_all import (
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

#!/usr/bin/env python3
"""統合バックアップスクリプト

Immich と Django の両方をバックアップする統合スクリプト。
コマンドライン引数で個別のバックアップも実行可能。
"""

import argparse
import sys
from datetime import datetime

try:
    # パッケージとして実行される場合（python -m scripts.backup_all）
    from .backup_django import main as backup_django_main
    from .backup_immich import main as backup_immich_main
except ImportError:
    # 直接実行される場合（python /app/scripts/backup_all.py）
    from backup_django import main as backup_django_main
    from backup_immich import main as backup_immich_main


def log_info(message: str) -> None:
    """INFO ログを出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [INFO] {message}")


def log_error(message: str) -> None:
    """ERROR ログを出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [ERROR] {message}", file=sys.stderr)


def log_success(message: str) -> None:
    """SUCCESS ログを出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [SUCCESS] {message}")


def run_immich_backup() -> int:
    """Immich バックアップを実行"""
    log_info("Immich バックアップを開始します...")
    try:
        result = backup_immich_main()
        if result == 0:
            log_success("Immich バックアップが完了しました")
        else:
            log_error("Immich バックアップが失敗しました")
        return result
    except Exception as e:
        log_error(f"Immich バックアップで予期しないエラーが発生しました: {e}")
        return 1


def run_django_backup() -> int:
    """Django バックアップを実行"""
    log_info("Django バックアップを開始します...")
    try:
        result = backup_django_main()
        if result == 0:
            log_success("Django バックアップが完了しました")
        else:
            log_error("Django バックアップが失敗しました")
        return result
    except Exception as e:
        log_error(f"Django バックアップで予期しないエラーが発生しました: {e}")
        return 1


def run_backup(immich: bool = True, django: bool = True) -> int:
    """バックアップを実行

    Args:
        immich: Immich バックアップを実行するか
        django: Django バックアップを実行するか

    Returns:
        0: すべてのバックアップが成功
        1: いずれかのバックアップが失敗
    """
    results = []

    if immich:
        results.append(run_immich_backup())

    if django:
        results.append(run_django_backup())

    # いずれかが失敗していたら 1 を返す
    return 1 if any(r != 0 for r in results) else 0


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(
        description="Immich と Django のバックアップを実行します"
    )
    parser.add_argument(
        "--immich-only",
        action="store_true",
        help="Immich のみバックアップを実行",
    )
    parser.add_argument(
        "--django-only",
        action="store_true",
        help="Django のみバックアップを実行",
    )
    return parser.parse_args()


def main() -> int:
    """メイン処理"""
    args = parse_args()

    log_info("##############################################")
    log_info("統合バックアップ処理を開始します")
    log_info("##############################################")

    # バックアップ対象を決定
    if args.immich_only:
        immich = True
        django = False
    elif args.django_only:
        immich = False
        django = True
    else:
        immich = True
        django = True

    result = run_backup(immich=immich, django=django)

    log_info("##############################################")
    if result == 0:
        log_success("すべてのバックアップ処理が正常に完了しました")
    else:
        log_error("バックアップ処理でエラーが発生しました")
    log_info("##############################################")

    return result


if __name__ == "__main__":
    sys.exit(main())

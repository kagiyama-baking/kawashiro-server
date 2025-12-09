#!/usr/bin/env python3
"""Immich リストアスクリプト"""

import argparse
import gzip
import os
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests


@dataclass
class RestoreConfig:
    """リストア設定"""

    db_hostname: str
    db_username: str
    db_password: str
    db_database_name: str
    django_api_url: str | None = None
    django_api_token: str | None = None
    onedrive_backup_path: str | None = None

    @classmethod
    def from_env(cls) -> "RestoreConfig":
        """環境変数から設定を読み込む"""
        required_vars = [
            "DB_HOSTNAME",
            "DB_USERNAME",
            "DB_PASSWORD",
            "DB_DATABASE_NAME",
        ]

        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            raise ValueError(
                f"必須環境変数 {', '.join(missing_vars)} が設定されていません"
            )

        return cls(
            db_hostname=os.environ["DB_HOSTNAME"],
            db_username=os.environ["DB_USERNAME"],
            db_password=os.environ["DB_PASSWORD"],
            db_database_name=os.environ["DB_DATABASE_NAME"],
            django_api_url=os.environ.get("DJANGO_API_URL"),
            django_api_token=os.environ.get("DJANGO_API_TOKEN"),
            onedrive_backup_path=os.environ.get("ONEDRIVE_BACKUP_PATH"),
        )


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


def log_warning(message: str) -> None:
    """WARNING ログを出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [WARNING] {message}")


def check_env_vars() -> RestoreConfig:
    """環境変数をチェックして設定を返す"""
    config = RestoreConfig.from_env()
    log_info("環境変数の確認が完了しました")
    return config


def check_onedrive_env_vars() -> RestoreConfig:
    """OneDrive 用の環境変数をチェックして設定を返す"""
    config = RestoreConfig.from_env()

    onedrive_vars = [
        "DJANGO_API_URL",
        "DJANGO_API_TOKEN",
        "ONEDRIVE_BACKUP_PATH",
    ]

    missing_vars = [var for var in onedrive_vars if not os.environ.get(var)]
    if missing_vars:
        raise ValueError(
            f"OneDriveからのダウンロードに必要な環境変数 {', '.join(missing_vars)} が設定されていません"
        )

    return config


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(
        description="Immich リストアスクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # データベースのみリストア（デフォルト）
  %(prog)s immich_db_20250127_120000.sql.gz
  %(prog)s --local immich_db_20250127_120000.sql.gz

  # データベースと写真データをリストア
  %(prog)s --with-data immich_db_20250127_120000.sql.gz

  # OneDriveからダウンロードしてリストア
  %(prog)s --from-onedrive immich_db_20250127_120000.sql.gz
  %(prog)s --from-onedrive --with-data immich_db_20250127_120000.sql.gz

注意:
  - リストアを実行する前に、必ずImmichサービスを停止してください
  - データベースの内容は完全に上書きされます
  - --with-dataを使用すると、写真データも完全に上書きされます
  - リストア前に現在のデータをバックアップすることを強く推奨します
""",
    )

    parser.add_argument(
        "backup_file",
        help="バックアップファイル名",
    )
    parser.add_argument(
        "--from-onedrive",
        action="store_true",
        dest="from_onedrive",
        help="OneDriveからバックアップファイルをダウンロードしてリストア",
    )
    parser.add_argument(
        "--local",
        action="store_false",
        dest="from_onedrive",
        help="ローカルのバックアップファイルからリストア（デフォルト）",
    )
    parser.add_argument(
        "--with-data",
        action="store_true",
        dest="with_data",
        help="写真データもリストアする（対応するdataファイルが必要）",
    )

    return parser.parse_args(args)


def generate_data_filename_from_db(db_filename: str) -> str:
    """データベースファイル名から写真データファイル名を生成する"""
    # immich_db_20250127_120000.sql.gz -> immich_data_20250127_120000.tar.gz
    return re.sub(r"immich_db_(.+)\.sql\.gz$", r"immich_data_\1.tar.gz", db_filename)


def download_from_onedrive(
    file_name: str,
    api_url: str,
    api_token: str,
    folder_path: str,
    local_dir: Path,
) -> Path:
    """OneDrive からファイルをダウンロードする"""
    remote_path = f"{folder_path}/{file_name}"
    local_path = local_dir / file_name

    log_info(f"OneDriveからファイルをダウンロードします: {remote_path}")

    endpoint = f"{api_url}/onedrive/download/"
    headers = {"Authorization": f"Token {api_token}"}

    try:
        response = requests.get(
            endpoint,
            params={"file_path": remote_path},
            headers=headers,
            stream=True,
            timeout=600,
        )

        if response.status_code == 200:
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = local_path.stat().st_size
            log_success(f"ファイルのダウンロードが完了しました: {local_path}")
            log_info(f"ダウンロードファイルサイズ: {file_size / 1024 / 1024:.2f} MB")

            return local_path
        else:
            raise RuntimeError(
                f"OneDriveからのダウンロードに失敗しました (HTTP {response.status_code}): "
                f"{response.text}"
            )

    except requests.RequestException as e:
        raise RuntimeError(f"OneDriveからのダウンロードに失敗しました: {e}") from e


def restore_database(
    backup_file: Path,
    hostname: str,
    username: str,
    password: str,
    database: str,
) -> bool:
    """PostgreSQL データベースをリストアする"""
    log_info("PostgreSQLデータベースのリストアを開始します...")

    if not backup_file.exists():
        raise RuntimeError(f"バックアップファイルが見つかりません: {backup_file}")

    file_size = backup_file.stat().st_size
    log_info(f"リストアファイルサイズ: {file_size / 1024 / 1024:.2f} MB")

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    # データベース接続確認
    log_info("データベース接続を確認しています...")
    result = subprocess.run(
        ["psql", "-h", hostname, "-U", username, "-d", "postgres", "-c", "SELECT 1"],
        capture_output=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("データベースサーバーへの接続に失敗しました")

    # 既存の接続を切断
    log_info("既存のデータベース接続を切断しています...")
    subprocess.run(
        [
            "psql",
            "-h",
            hostname,
            "-U",
            username,
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{database}' AND pid <> pg_backend_pid();",
        ],
        capture_output=True,
        env=env,
        check=False,
    )

    # データベースを削除して再作成
    log_info("データベースを再作成しています...")
    result = subprocess.run(
        [
            "psql",
            "-h",
            hostname,
            "-U",
            username,
            "-d",
            "postgres",
            "-c",
            f"DROP DATABASE IF EXISTS {database};",
        ],
        capture_output=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("データベースの削除に失敗しました")

    result = subprocess.run(
        [
            "psql",
            "-h",
            hostname,
            "-U",
            username,
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {database} OWNER {username};",
        ],
        capture_output=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("データベースの作成に失敗しました")

    # バックアップファイルをリストア
    log_info("バックアップファイルをリストアしています...")
    with gzip.open(backup_file, "rt") as f:
        sql_content = f.read()

    result = subprocess.run(
        ["psql", "-h", hostname, "-U", username, "-d", database],
        input=sql_content,
        capture_output=True,
        env=env,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"データベースのリストアに失敗しました: {result.stderr}")

    log_success("データベースのリストアが完了しました")
    return True


def restore_data(backup_file: Path, restore_dir: Path) -> bool:
    """写真データをリストアする"""
    log_info("写真データのリストアを開始します...")

    if not backup_file.exists():
        raise RuntimeError(
            f"写真データバックアップファイルが見つかりません: {backup_file}"
        )

    if not restore_dir.exists():
        raise RuntimeError(f"{restore_dir} ディレクトリが見つかりません")

    file_size = backup_file.stat().st_size
    log_info(f"リストアファイルサイズ: {file_size / 1024 / 1024:.2f} MB")

    # 既存のデータを一時バックアップ
    data_dir = restore_dir / "data"
    if data_dir.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_backup_dir = restore_dir / f"data.backup.{timestamp}"
        log_warning("既存の写真データを一時バックアップしています...")
        data_dir.rename(temp_backup_dir)
        log_info(f"既存データを一時バックアップしました: {temp_backup_dir}")
        log_info(f"リストア成功後、手動で削除してください: rm -rf {temp_backup_dir}")

    # バックアップファイルを展開
    log_info("写真データを展開しています...")
    with tarfile.open(backup_file, "r:gz") as tar:
        tar.extractall(path=restore_dir, filter="data")

    # 展開されたファイル数を表示
    file_count = sum(1 for _ in data_dir.rglob("*") if _.is_file())
    log_success("写真データのリストアが完了しました")
    log_info(f"リストアされたファイル数: {file_count}")

    return True


def cleanup_temp_file(file_path: Path, is_temp: bool) -> None:
    """一時ファイルを削除する"""
    if is_temp and file_path.exists():
        log_info(f"一時ファイルを削除しています: {file_path}")
        file_path.unlink()


def main() -> int:
    """メイン処理"""
    args = parse_args()

    # 環境変数のチェック
    try:
        config = check_env_vars()
    except ValueError as e:
        log_error(str(e))
        return 1

    # OneDrive からダウンロードする場合の追加チェック
    if args.from_onedrive:
        try:
            config = check_onedrive_env_vars()
        except ValueError as e:
            log_error(str(e))
            return 1

    backup_dir = Path("/backup")
    backup_dir.mkdir(parents=True, exist_ok=True)

    is_temp_file = False
    backup_file_path: Path

    if args.from_onedrive:
        try:
            backup_file_path = download_from_onedrive(
                file_name=args.backup_file,
                api_url=config.django_api_url,
                api_token=config.django_api_token,
                folder_path=config.onedrive_backup_path,
                local_dir=backup_dir,
            )
            is_temp_file = True
        except RuntimeError as e:
            log_error(str(e))
            return 1
    else:
        # ローカルファイルの場合
        if args.backup_file.startswith("/"):
            backup_file_path = Path(args.backup_file)
        else:
            backup_file_path = backup_dir / args.backup_file

        if not backup_file_path.exists():
            log_error(f"バックアップファイルが見つかりません: {backup_file_path}")
            return 1

    # リストアの確認
    log_warning("==================== 警告 ====================")
    log_warning("データベースをリストアします")
    log_warning("現在のデータベースの内容は完全に上書きされます")
    log_warning(f"バックアップファイル: {backup_file_path}")
    log_warning(f"対象データベース: {config.db_database_name}@{config.db_hostname}")
    log_warning("==============================================")

    # データベースをリストア
    try:
        restore_database(
            backup_file=backup_file_path,
            hostname=config.db_hostname,
            username=config.db_username,
            password=config.db_password,
            database=config.db_database_name,
        )
    except RuntimeError as e:
        log_error(str(e))
        cleanup_temp_file(backup_file_path, is_temp_file)
        return 1

    # 一時ファイルをクリーンアップ
    cleanup_temp_file(backup_file_path, is_temp_file)

    # 写真データもリストアする場合
    if args.with_data:
        log_info("写真データのリストアを準備しています...")

        data_file_name = generate_data_filename_from_db(args.backup_file)
        data_file_path: Path
        is_temp_data_file = False

        if args.from_onedrive:
            try:
                data_file_path = download_from_onedrive(
                    file_name=data_file_name,
                    api_url=config.django_api_url,
                    api_token=config.django_api_token,
                    folder_path=config.onedrive_backup_path,
                    local_dir=backup_dir,
                )
                is_temp_data_file = True
            except RuntimeError as e:
                log_error(str(e))
                return 1
        else:
            if data_file_name.startswith("/"):
                data_file_path = Path(data_file_name)
            else:
                data_file_path = backup_dir / data_file_name

            if not data_file_path.exists():
                log_warning(
                    f"写真データバックアップファイルが見つかりません: {data_file_path}"
                )
                log_warning("写真データのリストアをスキップします")
                data_file_path = None

        if data_file_path:
            restore_dir = Path("/restore")
            if not restore_dir.exists():
                log_error("/restore ディレクトリが見つかりません")
                log_error(
                    "docker-compose.ymlでImmichのdataボリュームを/restoreにマウントしてください"
                )
                cleanup_temp_file(data_file_path, is_temp_data_file)
                return 1

            try:
                restore_data(
                    backup_file=data_file_path,
                    restore_dir=restore_dir,
                )
            except RuntimeError as e:
                log_error(str(e))
                cleanup_temp_file(data_file_path, is_temp_data_file)
                return 1

            cleanup_temp_file(data_file_path, is_temp_data_file)

    log_success("==================== 完了 ====================")
    log_success("リストアが正常に完了しました")
    if args.with_data:
        log_success("データベースと写真データをリストアしました")
    else:
        log_success("データベースをリストアしました")
    log_success("Immichサービスを再起動してください")
    log_success("==============================================")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Immich バックアップスクリプト"""

import gzip
import os
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests


@dataclass
class BackupConfig:
    """バックアップ設定"""

    db_hostname: str
    db_username: str
    db_password: str
    db_database_name: str
    django_api_url: str
    django_api_token: str
    onedrive_backup_path: str
    backup_data: bool = False
    backup_retention_generations: int = 7

    @classmethod
    def from_env(cls) -> "BackupConfig":
        """環境変数から設定を読み込む"""
        required_vars = [
            "DB_HOSTNAME",
            "DB_USERNAME",
            "DB_PASSWORD",
            "DB_DATABASE_NAME",
            "DJANGO_API_URL",
            "DJANGO_API_TOKEN",
        ]

        # OneDrive パスは IMMICH_ONEDRIVE_BACKUP_PATH または ONEDRIVE_BACKUP_PATH のいずれか
        onedrive_path = os.environ.get("IMMICH_ONEDRIVE_BACKUP_PATH") or os.environ.get(
            "ONEDRIVE_BACKUP_PATH"
        )
        if not onedrive_path:
            required_vars.append("IMMICH_ONEDRIVE_BACKUP_PATH")

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
            django_api_url=os.environ["DJANGO_API_URL"],
            django_api_token=os.environ["DJANGO_API_TOKEN"],
            onedrive_backup_path=onedrive_path,
            backup_data=os.environ.get("BACKUP_DATA", "").lower() == "true",
            backup_retention_generations=int(
                os.environ.get("BACKUP_RETENTION_GENERATIONS", "7")
            ),
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


def check_env_vars() -> BackupConfig:
    """環境変数をチェックして設定を返す"""
    config = BackupConfig.from_env()
    log_info("環境変数の確認が完了しました")
    return config


def generate_backup_filename(backup_type: str, timestamp: str) -> str:
    """バックアップファイル名を生成する"""
    if backup_type == "db":
        return f"immich_db_{timestamp}.sql.gz"
    elif backup_type == "data":
        return f"immich_data_{timestamp}.tar.gz"
    else:
        raise ValueError(f"不明なバックアップタイプ: {backup_type}")


def backup_database(
    hostname: str,
    username: str,
    password: str,
    database: str,
    output_file: Path,
) -> bool:
    """PostgreSQL データベースをバックアップする"""
    log_info("PostgreSQLデータベースのバックアップを開始します...")

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    try:
        result = subprocess.run(
            [
                "pg_dump",
                "-h",
                hostname,
                "-U",
                username,
                "-d",
                database,
            ],
            capture_output=True,
            env=env,
            check=False,
        )

        if result.returncode != 0:
            error_msg = result.stderr.decode() if result.stderr else "不明なエラー"
            raise RuntimeError(f"データベースバックアップに失敗しました: {error_msg}")

        # gzip 圧縮して保存
        with gzip.open(output_file, "wb") as f:
            f.write(result.stdout)

        file_size = output_file.stat().st_size
        log_success(f"データベースバックアップが完了しました: {output_file}")
        log_info(f"バックアップファイルサイズ: {file_size / 1024 / 1024:.2f} MB")

        return True

    except FileNotFoundError as e:
        raise RuntimeError(
            "データベースバックアップに失敗しました: pg_dump が見つかりません"
        ) from e


def backup_data(source_dir: Path, output_file: Path) -> bool:
    """写真データをバックアップする"""
    log_info("写真データのバックアップを開始します...")

    if not source_dir.exists():
        raise RuntimeError(f"{source_dir} ディレクトリが見つかりません")

    with tarfile.open(output_file, "w:gz") as tar:
        tar.add(source_dir, arcname="data")

    file_size = output_file.stat().st_size
    log_success(f"写真データバックアップが完了しました: {output_file}")
    log_info(f"バックアップファイルサイズ: {file_size / 1024 / 1024:.2f} MB")

    return True


def upload_to_onedrive(
    file_path: Path,
    api_url: str,
    api_token: str,
    folder_path: str,
) -> bool:
    """OneDrive にファイルをアップロードする（ストリーミング）"""
    file_name = file_path.name
    file_size = file_path.stat().st_size
    log_info(
        f"OneDriveへのアップロードを開始します: {file_name} ({file_size / 1024 / 1024:.2f} MB)"
    )

    endpoint = f"{api_url}/onedrive/upload/"

    try:
        # requests-toolbelt の MultipartEncoder でストリーミングアップロード
        from requests_toolbelt import MultipartEncoder

        with open(file_path, "rb") as f:
            encoder = MultipartEncoder(
                fields={
                    "folder_path": folder_path,
                    "file_name": file_name,
                    "file": (file_name, f, "application/octet-stream"),
                }
            )
            headers = {
                "Authorization": f"Token {api_token}",
                "Content-Type": encoder.content_type,
            }

            response = requests.post(
                endpoint,
                data=encoder,
                headers=headers,
                timeout=7200,  # 2時間（大容量ファイル対応）
            )

        if response.status_code == 201:
            log_success(f"OneDriveへのアップロードが完了しました: {file_name}")
            log_info(f"レスポンス: {response.json()}")
            return True
        else:
            log_error(
                f"OneDriveへのアップロードに失敗しました (HTTP {response.status_code})"
            )
            log_error(f"レスポンス: {response.text}")
            return False

    except requests.RequestException as e:
        log_error(f"OneDriveへのアップロードに失敗しました: {e}")
        return False


def cleanup_local_backups(backup_dir: Path) -> int:
    """ローカルバックアップディレクトリを空にする"""
    log_info("バックアップ出力先ディレクトリを空にします...")

    deleted_count = 0
    for file_path in backup_dir.iterdir():
        if file_path.is_file():
            file_path.unlink()
            deleted_count += 1

    if deleted_count > 0:
        log_success(
            f"バックアップディレクトリから {deleted_count} 個のファイルを削除しました"
        )
    else:
        log_info("バックアップディレクトリにファイルはありませんでした")

    return deleted_count


def delete_old_files(
    files: list[dict],
    prefix: str,
    suffix: str,
    retention_generations: int,
    api_url: str,
    api_token: str,
    folder_path: str,
) -> int:
    """指定されたパターンの古いファイルを削除する"""
    # 対象ファイルをフィルタリング
    matching_files = [
        f["name"]
        for f in files
        if f["name"].startswith(prefix) and f["name"].endswith(suffix)
    ]

    if not matching_files:
        log_info(
            f"{prefix}*{suffix} のバックアップファイルはOneDrive上に見つかりませんでした"
        )
        return 0

    # 新しい順にソート
    matching_files.sort(reverse=True)

    file_count = len(matching_files)
    log_info(
        f"{prefix}*{suffix} のバックアップファイルが {file_count} 個見つかりました"
    )

    if file_count <= retention_generations:
        log_info(
            f"保持世代数（{retention_generations}）以内のため、削除対象のファイルはありません"
        )
        return 0

    # 古いファイルを削除
    files_to_delete = matching_files[retention_generations:]
    deleted_count = 0

    for file_name in files_to_delete:
        log_info(f"削除中: {file_name}")

        endpoint = f"{api_url}/onedrive/delete/"
        file_full_path = f"{folder_path}/{file_name}"
        encoded_path = quote(file_full_path, safe="/")

        headers = {"Authorization": f"Token {api_token}"}

        try:
            response = requests.delete(
                f"{endpoint}?file_path={encoded_path}&permanent_delete=true",
                headers=headers,
                timeout=60,
            )

            if response.status_code == 200:
                log_success(f"削除完了: {file_name}")
                deleted_count += 1
            else:
                log_error(f"削除失敗: {file_name} (HTTP {response.status_code})")

        except requests.RequestException as e:
            log_error(f"削除失敗: {file_name} ({e})")

    if deleted_count > 0:
        log_success(f"OneDrive上の古いバックアップを {deleted_count} 個削除しました")

    return deleted_count


def cleanup_old_onedrive_backups(
    api_url: str,
    api_token: str,
    folder_path: str,
    retention_generations: int,
    backup_data: bool,
) -> bool:
    """OneDrive 上の古いバックアップを削除する"""
    log_info(
        f"OneDrive上の古いバックアップを削除します（保持世代数: {retention_generations}）..."
    )

    endpoint = f"{api_url}/onedrive/list/"
    encoded_path = quote(folder_path, safe="/")
    headers = {"Authorization": f"Token {api_token}"}

    try:
        response = requests.get(
            f"{endpoint}?folder_path={encoded_path}",
            headers=headers,
            timeout=60,
        )

        if response.status_code != 200:
            log_error(
                f"OneDriveのファイル一覧取得に失敗しました (HTTP {response.status_code})"
            )
            log_error(f"レスポンス: {response.text}")
            return False

        files = response.json().get("files", [])

        # データベースバックアップファイルの削除
        delete_old_files(
            files=files,
            prefix="immich_db_",
            suffix=".sql.gz",
            retention_generations=retention_generations,
            api_url=api_url,
            api_token=api_token,
            folder_path=folder_path,
        )

        # 写真データバックアップファイルの削除
        if backup_data:
            delete_old_files(
                files=files,
                prefix="immich_data_",
                suffix=".tar.gz",
                retention_generations=retention_generations,
                api_url=api_url,
                api_token=api_token,
                folder_path=folder_path,
            )

        return True

    except requests.RequestException as e:
        log_error(f"OneDriveのファイル一覧取得に失敗しました: {e}")
        return False


def main() -> int:
    """メイン処理"""
    log_info("==========================================")
    log_info("Immichバックアップ処理を開始します")
    log_info("==========================================")

    # 環境変数のチェック
    try:
        config = check_env_vars()
    except ValueError as e:
        log_error(str(e))
        return 1

    # タイムスタンプ生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path("/backup")
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_backup_file = backup_dir / generate_backup_filename("db", timestamp)
    data_backup_file = backup_dir / generate_backup_filename("data", timestamp)

    upload_failed = False

    try:
        # 1. PostgreSQL バックアップ
        backup_database(
            hostname=config.db_hostname,
            username=config.db_username,
            password=config.db_password,
            database=config.db_database_name,
            output_file=db_backup_file,
        )

        # 2. 写真データバックアップ（オプション）
        if config.backup_data:
            backup_data(
                source_dir=Path("/source/data"),
                output_file=data_backup_file,
            )
        else:
            log_info(
                f"写真データのバックアップはスキップします (BACKUP_DATA={config.backup_data})"
            )

        # 3. OneDrive へアップロード
        log_info("------------------------------------------")
        log_info("OneDriveへのアップロードを開始します")
        log_info("------------------------------------------")

        if not upload_to_onedrive(
            file_path=db_backup_file,
            api_url=config.django_api_url,
            api_token=config.django_api_token,
            folder_path=config.onedrive_backup_path,
        ):
            upload_failed = True

        if (
            config.backup_data
            and data_backup_file.exists()
            and not upload_to_onedrive(
                file_path=data_backup_file,
                api_url=config.django_api_url,
                api_token=config.django_api_token,
                folder_path=config.onedrive_backup_path,
            )
        ):
            upload_failed = True

    except RuntimeError as e:
        log_error(str(e))
        upload_failed = True

    # 4. ローカルバックアップのクリーンアップ
    log_info("------------------------------------------")
    log_info("ローカルバックアップのクリーンアップ")
    log_info("------------------------------------------")
    cleanup_local_backups(backup_dir)

    # 5. OneDrive 上の古いバックアップの削除
    if not upload_failed:
        log_info("------------------------------------------")
        log_info("OneDrive上の古いバックアップのクリーンアップ")
        log_info("------------------------------------------")
        cleanup_old_onedrive_backups(
            api_url=config.django_api_url,
            api_token=config.django_api_token,
            folder_path=config.onedrive_backup_path,
            retention_generations=config.backup_retention_generations,
            backup_data=config.backup_data,
        )
    else:
        log_info("------------------------------------------")
        log_info(
            "OneDrive上の古いバックアップのクリーンアップをスキップします（アップロード失敗のため）"
        )
        log_info("------------------------------------------")

    log_info("==========================================")
    if not upload_failed:
        log_success("バックアップ処理が正常に完了しました")
    else:
        log_error("バックアップ処理が失敗しました（アップロードエラー）")
    log_info("==========================================")

    return 1 if upload_failed else 0


if __name__ == "__main__":
    sys.exit(main())

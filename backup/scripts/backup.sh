#!/bin/bash
set -e  # エラー時に即座に終了

# ============================================================
# Immich バックアップスクリプト
# ============================================================

# 色付きログ出力用の関数
log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" >&2
}

log_success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SUCCESS] $1"
}

# 環境変数のチェック
check_env_vars() {
    local required_vars=(
        "DB_HOSTNAME"
        "DB_USERNAME"
        "DB_PASSWORD"
        "DB_DATABASE_NAME"
        "DJANGO_API_URL"
        "DJANGO_API_TOKEN"
        "ONEDRIVE_BACKUP_PATH"
    )

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            log_error "必須環境変数 $var が設定されていません"
            exit 1
        fi
    done

    log_info "環境変数の確認が完了しました"
}

# タイムスタンプの生成
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_DIR="/backup"
DB_BACKUP_FILE="${BACKUP_DIR}/immich_db_${TIMESTAMP}.sql.gz"
DATA_BACKUP_FILE="${BACKUP_DIR}/immich_data_${TIMESTAMP}.tar.gz"

# ============================================================
# 1. PostgreSQLバックアップ
# ============================================================
backup_database() {
    log_info "PostgreSQLデータベースのバックアップを開始します..."

    # PGPASSWORD環境変数を設定してパスワードを渡す
    export PGPASSWORD="${DB_PASSWORD}"

    # pg_dumpを実行して圧縮
    if pg_dump -h "${DB_HOSTNAME}" -U "${DB_USERNAME}" -d "${DB_DATABASE_NAME}" | gzip > "${DB_BACKUP_FILE}"; then
        log_success "データベースバックアップが完了しました: ${DB_BACKUP_FILE}"

        # ファイルサイズを表示
        local file_size=$(du -h "${DB_BACKUP_FILE}" | cut -f1)
        log_info "バックアップファイルサイズ: ${file_size}"
    else
        log_error "データベースバックアップに失敗しました"
        exit 1
    fi

    # PGPASSWORD環境変数をクリア
    unset PGPASSWORD
}

# ============================================================
# 2. 写真データのバックアップ（オプション）
# ============================================================
backup_data() {
    if [ "${BACKUP_DATA}" = "true" ]; then
        log_info "写真データのバックアップを開始します..."

        # /source/dataディレクトリが存在するか確認
        if [ ! -d "/source/data" ]; then
            log_error "/source/data ディレクトリが見つかりません"
            exit 1
        fi

        # tar.gzで圧縮
        if tar -czf "${DATA_BACKUP_FILE}" -C /source data; then
            log_success "写真データバックアップが完了しました: ${DATA_BACKUP_FILE}"

            # ファイルサイズを表示
            local file_size=$(du -h "${DATA_BACKUP_FILE}" | cut -f1)
            log_info "バックアップファイルサイズ: ${file_size}"
        else
            log_error "写真データバックアップに失敗しました"
            exit 1
        fi
    else
        log_info "写真データのバックアップはスキップします (BACKUP_DATA=${BACKUP_DATA})"
    fi
}

# ============================================================
# 3. Django APIへのアップロード
# ============================================================
upload_to_onedrive() {
    local file_path=$1
    local file_name=$(basename "${file_path}")

    log_info "OneDriveへのアップロードを開始します: ${file_name}"

    # Django APIエンドポイント
    local api_endpoint="${DJANGO_API_URL}/onedrive/upload/"

    # curlでファイルをアップロード
    local response=$(curl -s -w "\n%{http_code}" -X POST "${api_endpoint}" \
        -H "Authorization: Token ${DJANGO_API_TOKEN}" \
        -F "file=@${file_path}" \
        -F "folder_path=${ONEDRIVE_BACKUP_PATH}" \
        -F "file_name=${file_name}")

    # HTTPステータスコードを取得（最後の行）
    local http_code=$(echo "${response}" | tail -n1)
    # レスポンスボディを取得（最後の行を除く）
    local response_body=$(echo "${response}" | sed '$d')

    if [ "${http_code}" -eq 201 ]; then
        log_success "OneDriveへのアップロードが完了しました: ${file_name}"
        log_info "レスポンス: ${response_body}"
    else
        log_error "OneDriveへのアップロードに失敗しました (HTTP ${http_code})"
        log_error "レスポンス: ${response_body}"
        exit 1
    fi
}

# ============================================================
# 4. 古いローカルバックアップの削除
# ============================================================
cleanup_old_backups() {
    local retention_days=${BACKUP_RETENTION_DAYS:-7}

    log_info "${retention_days}日より古いバックアップファイルを削除します..."

    # データベースバックアップの削除
    local deleted_count=$(find "${BACKUP_DIR}" -name "immich_db_*.sql.gz" -type f -mtime +${retention_days} -delete -print | wc -l)
    if [ "${deleted_count}" -gt 0 ]; then
        log_info "古いデータベースバックアップを ${deleted_count} 個削除しました"
    else
        log_info "削除対象の古いデータベースバックアップはありませんでした"
    fi

    # 写真データバックアップの削除
    if [ "${BACKUP_DATA}" = "true" ]; then
        deleted_count=$(find "${BACKUP_DIR}" -name "immich_data_*.tar.gz" -type f -mtime +${retention_days} -delete -print | wc -l)
        if [ "${deleted_count}" -gt 0 ]; then
            log_info "古い写真データバックアップを ${deleted_count} 個削除しました"
        else
            log_info "削除対象の古い写真データバックアップはありませんでした"
        fi
    fi
}

# ============================================================
# メイン処理
# ============================================================
main() {
    log_info "=========================================="
    log_info "Immichバックアップ処理を開始します"
    log_info "=========================================="

    # 環境変数のチェック
    check_env_vars

    # バックアップディレクトリの作成
    mkdir -p "${BACKUP_DIR}"

    # 1. PostgreSQLバックアップ
    backup_database

    # 2. 写真データのバックアップ（オプション）
    backup_data

    # 3. OneDriveへアップロード
    log_info "------------------------------------------"
    log_info "OneDriveへのアップロードを開始します"
    log_info "------------------------------------------"

    # データベースバックアップをアップロード
    upload_to_onedrive "${DB_BACKUP_FILE}"

    # 写真データバックアップをアップロード（存在する場合）
    if [ -f "${DATA_BACKUP_FILE}" ]; then
        upload_to_onedrive "${DATA_BACKUP_FILE}"
    fi

    # 4. 古いローカルバックアップの削除
    log_info "------------------------------------------"
    log_info "古いバックアップファイルのクリーンアップ"
    log_info "------------------------------------------"
    cleanup_old_backups

    log_info "=========================================="
    log_success "バックアップ処理が正常に完了しました"
    log_info "=========================================="
}

# スクリプト実行
main

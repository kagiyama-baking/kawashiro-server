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
# 4. ローカルバックアップディレクトリのクリーンアップ
# ============================================================
cleanup_local_backups() {
    log_info "バックアップ出力先ディレクトリを空にします..."

    # バックアップディレクトリ内のすべてのファイルを削除
    local deleted_count=$(find "${BACKUP_DIR}" -type f -delete -print | wc -l)

    if [ "${deleted_count}" -gt 0 ]; then
        log_success "バックアップディレクトリから ${deleted_count} 個のファイルを削除しました"
    else
        log_info "バックアップディレクトリにファイルはありませんでした"
    fi
}

# ============================================================
# 5. OneDrive上の古いバックアップの削除
# ============================================================
cleanup_old_onedrive_backups() {
    local retention_generations=${BACKUP_RETENTION_GENERATIONS:-7}

    log_info "OneDrive上の古いバックアップを削除します（保持世代数: ${retention_generations}）..."

    # Django APIエンドポイント
    local api_endpoint="${DJANGO_API_URL}/onedrive/list/"

    # OneDriveのバックアップフォルダ内のファイル一覧を取得
    local response=$(curl -s -w "\n%{http_code}" -X GET "${api_endpoint}?folder_path=${ONEDRIVE_BACKUP_PATH}" \
        -H "Authorization: Token ${DJANGO_API_TOKEN}")

    # HTTPステータスコードを取得
    local http_code=$(echo "${response}" | tail -n1)
    local response_body=$(echo "${response}" | sed '$d')

    if [ "${http_code}" -ne 200 ]; then
        log_error "OneDriveのファイル一覧取得に失敗しました (HTTP ${http_code})"
        log_error "レスポンス: ${response_body}"
        return 1
    fi

    # データベースバックアップファイルの削除
    delete_old_files "immich_db_" ".sql.gz" "${retention_generations}" "${response_body}"

    # 写真データバックアップファイルの削除（BACKUP_DATAがtrueの場合）
    if [ "${BACKUP_DATA}" = "true" ]; then
        delete_old_files "immich_data_" ".tar.gz" "${retention_generations}" "${response_body}"
    fi
}

# ============================================================
# 指定されたパターンの古いファイルを削除
# ============================================================
delete_old_files() {
    local prefix=$1
    local suffix=$2
    local retention_generations=$3
    local files_json=$4

    # jqを使用してファイル名をフィルタリングし、作成日時でソート
    # 該当するファイル名のリストを取得（新しい順）
    local files=$(echo "${files_json}" | grep -o "\"name\":\"${prefix}[^\"]*${suffix}\"" | sed 's/"name":"\(.*\)"/\1/' | sort -r)

    if [ -z "${files}" ]; then
        log_info "${prefix}*${suffix} のバックアップファイルはOneDrive上に見つかりませんでした"
        return 0
    fi

    local file_count=$(echo "${files}" | wc -l)
    log_info "${prefix}*${suffix} のバックアップファイルが ${file_count} 個見つかりました"

    # 保持世代数を超えるファイルを削除
    if [ "${file_count}" -le "${retention_generations}" ]; then
        log_info "保持世代数（${retention_generations}）以内のため、削除対象のファイルはありません"
        return 0
    fi

    # 古いファイル（保持世代数を超えるファイル）を削除
    local files_to_delete=$(echo "${files}" | tail -n +$((retention_generations + 1)))
    local delete_count=0

    while IFS= read -r file_name; do
        [ -z "${file_name}" ] && continue

        log_info "削除中: ${file_name}"

        local delete_endpoint="${DJANGO_API_URL}/onedrive/delete/"
        local file_path="${ONEDRIVE_BACKUP_PATH}/${file_name}"

        # 完全削除オプション（permanent_delete=true）を指定
        local delete_response=$(curl -s -w "\n%{http_code}" -X DELETE "${delete_endpoint}?file_path=${file_path}&permanent_delete=true" \
            -H "Authorization: Token ${DJANGO_API_TOKEN}")

        local delete_http_code=$(echo "${delete_response}" | tail -n1)

        if [ "${delete_http_code}" -eq 200 ]; then
            log_success "削除完了: ${file_name}"
            delete_count=$((delete_count + 1))
        else
            log_error "削除失敗: ${file_name} (HTTP ${delete_http_code})"
        fi
    done <<< "${files_to_delete}"

    if [ "${delete_count}" -gt 0 ]; then
        log_success "OneDrive上の古いバックアップを ${delete_count} 個削除しました"
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

    # 4. ローカルバックアップディレクトリのクリーンアップ
    log_info "------------------------------------------"
    log_info "ローカルバックアップのクリーンアップ"
    log_info "------------------------------------------"
    cleanup_local_backups

    # 5. OneDrive上の古いバックアップの削除
    log_info "------------------------------------------"
    log_info "OneDrive上の古いバックアップのクリーンアップ"
    log_info "------------------------------------------"
    cleanup_old_onedrive_backups

    log_info "=========================================="
    log_success "バックアップ処理が正常に完了しました"
    log_info "=========================================="
}

# スクリプト実行
main

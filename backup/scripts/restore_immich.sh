#!/bin/bash
set -e  # エラー時に即座に終了

# ============================================================
# Immich リストアスクリプト
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

log_warning() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARNING] $1"
}

# 使用方法を表示
usage() {
    cat << EOF
使用方法:
  $0 [OPTIONS] <バックアップファイル名>

OPTIONS:
  --from-onedrive    OneDriveからバックアップファイルをダウンロードしてリストア
  --local            ローカルのバックアップファイルからリストア（デフォルト）
  --with-data        写真データもリストアする（対応するdataファイルが必要）
  --help             このヘルプを表示

例:
  # データベースのみリストア（デフォルト）
  $0 immich_db_20250127_120000.sql.gz
  $0 --local immich_db_20250127_120000.sql.gz

  # データベースと写真データをリストア
  $0 --with-data immich_db_20250127_120000.sql.gz

  # OneDriveからダウンロードしてリストア
  $0 --from-onedrive immich_db_20250127_120000.sql.gz
  $0 --from-onedrive --with-data immich_db_20250127_120000.sql.gz

注意:
  - リストアを実行する前に、必ずImmichサービスを停止してください
  - データベースの内容は完全に上書きされます
  - --with-dataを使用すると、写真データも完全に上書きされます
  - リストア前に現在のデータをバックアップすることを強く推奨します
EOF
    exit 0
}

# 環境変数のチェック
check_env_vars() {
    local required_vars=(
        "DB_HOSTNAME"
        "DB_USERNAME"
        "DB_PASSWORD"
        "DB_DATABASE_NAME"
    )

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            log_error "必須環境変数 $var が設定されていません"
            exit 1
        fi
    done

    log_info "環境変数の確認が完了しました"
}

# OneDrive用の環境変数をチェック
check_onedrive_env_vars() {
    local required_vars=(
        "DJANGO_API_URL"
        "DJANGO_API_TOKEN"
        "ONEDRIVE_BACKUP_PATH"
    )

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            log_error "OneDriveからのダウンロードに必要な環境変数 $var が設定されていません"
            exit 1
        fi
    done
}

# OneDriveからファイルをダウンロード
download_from_onedrive() {
    local file_name="$1"
    local remote_path="${ONEDRIVE_BACKUP_PATH}/${file_name}"
    local local_path="/backup/${file_name}"

    log_info "OneDriveからファイルをダウンロードします: ${remote_path}"

    # Django APIを使ってダウンロード
    local api_endpoint="${DJANGO_API_URL}/onedrive/download/"

    # curlでファイルをダウンロード
    local http_code=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: Token ${DJANGO_API_TOKEN}" \
        -G --data-urlencode "file_path=${remote_path}" \
        -o "${local_path}" \
        "${api_endpoint}" | tail -n1)

    if [ "${http_code}" -eq 200 ]; then
        log_success "ファイルのダウンロードが完了しました: ${local_path}"

        # ファイルサイズを表示
        local file_size=$(du -h "${local_path}" | cut -f1)
        log_info "ダウンロードファイルサイズ: ${file_size}"

        echo "${local_path}"
    else
        log_error "OneDriveからのダウンロードに失敗しました (HTTP ${http_code})"
        # エラーレスポンスを表示
        if [ -f "${local_path}" ]; then
            cat "${local_path}" >&2
            rm -f "${local_path}"
        fi
        exit 1
    fi
}

# データベースのバックアップを確認
confirm_restore() {
    local backup_file="$1"

    log_warning "==================== 警告 ===================="
    log_warning "データベースをリストアします"
    log_warning "現在のデータベースの内容は完全に上書きされます"
    log_warning "バックアップファイル: ${backup_file}"
    log_warning "対象データベース: ${DB_DATABASE_NAME}@${DB_HOSTNAME}"
    log_warning "=============================================="

    read -p "本当にリストアを実行しますか？ (yes/no): " confirmation

    if [ "${confirmation}" != "yes" ]; then
        log_info "リストアをキャンセルしました"
        exit 0
    fi
}

# PostgreSQLデータベースのリストア
restore_database() {
    local backup_file="$1"

    log_info "PostgreSQLデータベースのリストアを開始します..."

    # ファイルの存在確認
    if [ ! -f "${backup_file}" ]; then
        log_error "バックアップファイルが見つかりません: ${backup_file}"
        exit 1
    fi

    # ファイルサイズを表示
    local file_size=$(du -h "${backup_file}" | cut -f1)
    log_info "リストアファイルサイズ: ${file_size}"

    # PGPASSWORD環境変数を設定してパスワードを渡す
    export PGPASSWORD="${DB_PASSWORD}"

    # データベースが存在するか確認
    log_info "データベース接続を確認しています..."
    if ! psql -h "${DB_HOSTNAME}" -U "${DB_USERNAME}" -d postgres -c "SELECT 1" > /dev/null 2>&1; then
        log_error "データベースサーバーへの接続に失敗しました"
        unset PGPASSWORD
        exit 1
    fi

    # 既存の接続を切断
    log_info "既存のデータベース接続を切断しています..."
    psql -h "${DB_HOSTNAME}" -U "${DB_USERNAME}" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_DATABASE_NAME}' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true

    # データベースを削除して再作成
    log_info "データベースを再作成しています..."
    psql -h "${DB_HOSTNAME}" -U "${DB_USERNAME}" -d postgres -c "DROP DATABASE IF EXISTS ${DB_DATABASE_NAME};" || {
        log_error "データベースの削除に失敗しました"
        unset PGPASSWORD
        exit 1
    }

    psql -h "${DB_HOSTNAME}" -U "${DB_USERNAME}" -d postgres -c "CREATE DATABASE ${DB_DATABASE_NAME} OWNER ${DB_USERNAME};" || {
        log_error "データベースの作成に失敗しました"
        unset PGPASSWORD
        exit 1
    }

    # バックアップファイルをリストア
    log_info "バックアップファイルをリストアしています..."
    if gunzip -c "${backup_file}" | psql -h "${DB_HOSTNAME}" -U "${DB_USERNAME}" -d "${DB_DATABASE_NAME}" > /dev/null 2>&1; then
        log_success "データベースのリストアが完了しました"
    else
        log_error "データベースのリストアに失敗しました"
        unset PGPASSWORD
        exit 1
    fi

    # PGPASSWORD環境変数をクリア
    unset PGPASSWORD
}

# 写真データのリストア
restore_data() {
    local backup_file="$1"

    log_info "写真データのリストアを開始します..."

    # ファイルの存在確認
    if [ ! -f "${backup_file}" ]; then
        log_error "写真データバックアップファイルが見つかりません: ${backup_file}"
        exit 1
    fi

    # ファイルサイズを表示
    local file_size=$(du -h "${backup_file}" | cut -f1)
    log_info "リストアファイルサイズ: ${file_size}"

    # リストア先ディレクトリ
    local restore_dir="/restore/data"

    # リストア先ディレクトリが存在しない場合は作成
    if [ ! -d "/restore" ]; then
        log_error "/restore ディレクトリが見つかりません"
        log_error "docker-compose.ymlでImmichのdataボリュームを/restoreにマウントしてください"
        exit 1
    fi

    # 既存のデータを削除
    log_warning "既存の写真データを削除しています..."
    if [ -d "${restore_dir}" ]; then
        rm -rf "${restore_dir}"
    fi

    # バックアップファイルを展開
    log_info "写真データを展開しています..."
    if tar -xzf "${backup_file}" -C /restore; then
        log_success "写真データのリストアが完了しました"

        # 展開されたファイル数を表示
        local file_count=$(find "${restore_dir}" -type f 2>/dev/null | wc -l)
        log_info "リストアされたファイル数: ${file_count}"
    else
        log_error "写真データのリストアに失敗しました"
        exit 1
    fi
}

# クリーンアップ（OneDriveからダウンロードした一時ファイルを削除）
cleanup_temp_file() {
    local file_path="$1"
    local is_temp="$2"

    if [ "${is_temp}" = "true" ] && [ -f "${file_path}" ]; then
        log_info "一時ファイルを削除しています: ${file_path}"
        rm -f "${file_path}"
    fi
}

# ============================================================
# メイン処理
# ============================================================

# 引数のパース
FROM_ONEDRIVE=false
WITH_DATA=false
BACKUP_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --from-onedrive)
            FROM_ONEDRIVE=true
            shift
            ;;
        --local)
            FROM_ONEDRIVE=false
            shift
            ;;
        --with-data)
            WITH_DATA=true
            shift
            ;;
        --help)
            usage
            ;;
        -*)
            log_error "不明なオプション: $1"
            usage
            ;;
        *)
            BACKUP_FILE="$1"
            shift
            ;;
    esac
done

# バックアップファイル名が指定されているか確認
if [ -z "${BACKUP_FILE}" ]; then
    log_error "バックアップファイル名が指定されていません"
    usage
fi

# 環境変数のチェック
check_env_vars

# OneDriveからダウンロードする場合
IS_TEMP_FILE=false
if [ "${FROM_ONEDRIVE}" = "true" ]; then
    check_onedrive_env_vars
    BACKUP_FILE_PATH=$(download_from_onedrive "${BACKUP_FILE}")
    IS_TEMP_FILE=true
else
    # ローカルファイルの場合、フルパスを生成
    if [[ "${BACKUP_FILE}" = /* ]]; then
        BACKUP_FILE_PATH="${BACKUP_FILE}"
    else
        BACKUP_FILE_PATH="/backup/${BACKUP_FILE}"
    fi

    # ファイルの存在確認
    if [ ! -f "${BACKUP_FILE_PATH}" ]; then
        log_error "バックアップファイルが見つかりません: ${BACKUP_FILE_PATH}"
        exit 1
    fi
fi

# リストアの確認
confirm_restore "${BACKUP_FILE_PATH}"

# データベースをリストア
restore_database "${BACKUP_FILE_PATH}"

# 一時ファイルをクリーンアップ
cleanup_temp_file "${BACKUP_FILE_PATH}" "${IS_TEMP_FILE}"

# 写真データもリストアする場合
DATA_FILE_PATH=""
IS_TEMP_DATA_FILE=false
if [ "${WITH_DATA}" = "true" ]; then
    log_info "写真データのリストアを準備しています..."

    # データベースファイル名から写真データファイル名を生成
    # immich_db_20250127_120000.sql.gz -> immich_data_20250127_120000.tar.gz
    local data_file_name=$(echo "${BACKUP_FILE}" | sed 's/immich_db_/immich_data_/' | sed 's/\.sql\.gz$/\.tar\.gz/')

    if [ "${FROM_ONEDRIVE}" = "true" ]; then
        # OneDriveからダウンロード
        DATA_FILE_PATH=$(download_from_onedrive "${data_file_name}")
        IS_TEMP_DATA_FILE=true
    else
        # ローカルファイルの場合、フルパスを生成
        if [[ "${data_file_name}" = /* ]]; then
            DATA_FILE_PATH="${data_file_name}"
        else
            DATA_FILE_PATH="/backup/${data_file_name}"
        fi

        # ファイルの存在確認
        if [ ! -f "${DATA_FILE_PATH}" ]; then
            log_warning "写真データバックアップファイルが見つかりません: ${DATA_FILE_PATH}"
            log_warning "写真データのリストアをスキップします"
        else
            restore_data "${DATA_FILE_PATH}"
            cleanup_temp_file "${DATA_FILE_PATH}" "${IS_TEMP_DATA_FILE}"
        fi
    fi

    # OneDriveからダウンロードした場合は必ず存在するのでリストア実行
    if [ "${FROM_ONEDRIVE}" = "true" ] && [ -f "${DATA_FILE_PATH}" ]; then
        restore_data "${DATA_FILE_PATH}"
        cleanup_temp_file "${DATA_FILE_PATH}" "${IS_TEMP_DATA_FILE}"
    fi
fi

log_success "==================== 完了 ===================="
log_success "リストアが正常に完了しました"
if [ "${WITH_DATA}" = "true" ]; then
    log_success "データベースと写真データをリストアしました"
else
    log_success "データベースをリストアしました"
fi
log_success "Immichサービスを再起動してください"
log_success "=============================================="

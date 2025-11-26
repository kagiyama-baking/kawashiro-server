#!/bin/bash
#
# Immichバックアップスクリプト
#
# 【説明】
#   Immichの全データ（PostgreSQLデータベース、写真・動画、Redis、ML Cache）をバックアップします。
#   オプションで、バックアップファイルをOneDriveにアップロードできます。
#
# 【前提条件】
#   - Docker Composeでimmichが起動していること
#   - .envファイルにDB_USERNAMEとDB_DATABASE_NAMEが設定されていること
#   - 十分なディスク容量があること
#   - (OneDriveアップロード時) DJANGO_API_TOKENが.envに設定されていること
#
# 【使用方法】
#   ./scripts/immich-backup.sh
#
# 【バックアップ先】
#   ローカル: ./volumes/backups/immich-backup-YYYYMMDD_HHMMSS/
#   OneDrive: /kagiyama-baking/Servers/KawashiroServer/immich-backup-YYYYMMDD_HHMMSS/
#
# 【バックアップファイル】
#   - immich-postgres-database.sql.gz: PostgreSQLデータベースダンプ（圧縮）
#   - immich-data.tar.gz: Immichデータ（写真・動画・サムネイル等）
#   - immich-postgres-volume.tar.gz: PostgreSQLボリューム全体
#   - immich-env: 環境変数設定ファイル
#
# 【OneDriveアップロード設定】
#   .envファイルに以下を追加:
#     DJANGO_API_TOKEN=your_token_here
#     DJANGO_API_URL=http://localhost:8000  # オプション（デフォルト値あり）
#     ONEDRIVE_BACKUP_PATH=/kagiyama-baking/Servers/KawashiroServer  # オプション
#
# 【リストア方法】
#   ./scripts/immich-restore.sh <バックアップディレクトリ>
#
set -e

# 環境変数を読み込む
if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

# デフォルト値の設定
DB_USERNAME="${DB_USERNAME:-immich}"
DB_DATABASE_NAME="${DB_DATABASE_NAME:-immich}"

# バックアップディレクトリの設定
BACKUP_BASE_DIR="./volumes/backups"
BACKUP_DIR="$BACKUP_BASE_DIR/immich-backup-$(date +%Y%m%d_%H%M%S)"

# バックアップディレクトリを作成
mkdir -p "$BACKUP_DIR"

echo "=== Immich バックアップ開始 ==="
echo "バックアップ先: $BACKUP_DIR"
echo "データベースユーザー: $DB_USERNAME"
echo "データベース名: $DB_DATABASE_NAME"

# 1. PostgreSQLデータベースのバックアップ
echo "PostgreSQLデータベースをバックアップ中..."
# 特定のデータベースのみをバックアップ（DROP文なし）し、圧縮する
docker exec -t immich-postgres pg_dump -U "$DB_USERNAME" -d "$DB_DATABASE_NAME" --clean --if-exists | gzip > "$BACKUP_DIR/immich-postgres-database.sql.gz"
echo "✓ データベースバックアップ完了"

# 2. Immichデータ（写真・動画・サムネイル等）のバックアップ
echo "Immichデータをバックアップ中..."
# volumes/immich/dataディレクトリをバックアップ（docker-compose.ymlの設定に基づく）
if [ -d "./volumes/immich/data" ]; then
    tar czf "$BACKUP_DIR/immich-data.tar.gz" -C ./volumes/immich data
    echo "✓ Immichデータバックアップ完了"
else
    echo "警告: ./volumes/immich/dataが見つかりません"
fi

# 3. PostgreSQLボリュームのバックアップ（追加の安全性のため）
echo "PostgreSQLボリュームをバックアップ中..."
docker run --rm \
  -v immich-pgdata:/source:ro \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine tar czf /backup/immich-postgres-volume.tar.gz -C /source .
echo "✓ PostgreSQLボリュームバックアップ完了"

# 4. 設定ファイルのバックアップ
echo "設定ファイルをバックアップ中..."
if [ -f ".env" ]; then
  cp .env "$BACKUP_DIR/immich-env"
fi
echo "✓ 設定ファイルバックアップ完了"

# バックアップ完了情報を表示
echo ""
echo "=== バックアップ完了 ==="
echo "バックアップディレクトリ: $BACKUP_DIR"
echo "バックアップサイズ:"
du -sh "$BACKUP_DIR"
echo ""
echo "バックアップ内容:"
ls -lh "$BACKUP_DIR"

# 5. OneDriveへのアップロード（オプション）
echo ""
echo "=== OneDriveへのアップロード ==="

# 環境変数からAPI設定を読み込む
DJANGO_API_URL="${DJANGO_API_URL:-http://localhost:8000}"
DJANGO_API_TOKEN="${DJANGO_API_TOKEN}"
ONEDRIVE_BACKUP_PATH="${ONEDRIVE_BACKUP_PATH:-/kagiyama-baking/Servers/KawashiroServer}"

if [ -z "$DJANGO_API_TOKEN" ]; then
  echo "警告: DJANGO_API_TOKENが設定されていません。OneDriveへのアップロードをスキップします。"
  echo "OneDriveにアップロードする場合は、.envファイルにDJANGO_API_TOKENを設定してください。"
else
  echo "OneDriveへバックアップファイルをアップロード中..."
  UPLOAD_SUCCESS=true

  # バックアップディレクトリ名を取得
  BACKUP_DIR_NAME=$(basename "$BACKUP_DIR")
  ONEDRIVE_FOLDER="$ONEDRIVE_BACKUP_PATH/$BACKUP_DIR_NAME"

  # バックアップディレクトリ内の各ファイルをアップロード
  for file in "$BACKUP_DIR"/*; do
    if [ -f "$file" ]; then
      filename=$(basename "$file")
      echo "  アップロード中: $filename"

      response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Authorization: Token $DJANGO_API_TOKEN" \
        -F "file=@$file" \
        -F "folder_path=$ONEDRIVE_FOLDER" \
        -F "file_name=$filename" \
        "$DJANGO_API_URL/onedrive/upload/")

      http_code=$(echo "$response" | tail -n1)
      response_body=$(echo "$response" | sed '$d')

      if [ "$http_code" = "201" ]; then
        echo "  ✓ $filename のアップロード完了"
      else
        echo "  ✗ $filename のアップロード失敗 (HTTP $http_code)"
        echo "  エラー詳細: $response_body"
        UPLOAD_SUCCESS=false
      fi
    fi
  done

  if [ "$UPLOAD_SUCCESS" = true ]; then
    echo "✓ すべてのファイルのOneDriveアップロード完了"
    echo "OneDrive保存先: $ONEDRIVE_FOLDER"
  else
    echo "⚠ 一部のファイルのアップロードに失敗しました"
  fi
fi

echo ""
echo "バックアップが正常に完了しました。"
echo "リストアする場合: ./scripts/immich-restore.sh $BACKUP_DIR"
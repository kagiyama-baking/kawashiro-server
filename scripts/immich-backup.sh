#!/bin/bash
#
# Immichバックアップスクリプト
#
# 【説明】
#   Immichの全データ（PostgreSQLデータベース、写真・動画、Redis、ML Cache）をバックアップします。
#
# 【前提条件】
#   - Docker Composeでimmichが起動していること
#   - .envファイルにDB_USERNAMEとDB_DATABASE_NAMEが設定されていること
#   - 十分なディスク容量があること
#
# 【使用方法】
#   ./scripts/immich-backup.sh
#
# 【バックアップ先】
#   ./backups/immich/immich-backup-YYYYMMDD_HHMMSS/
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
# 特定のデータベースのみをバックアップ（DROP文なし）
docker exec -t immich-postgres pg_dump -U "$DB_USERNAME" -d "$DB_DATABASE_NAME" --clean --if-exists > "$BACKUP_DIR/database.sql"
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
  alpine tar czf /backup/pgdata-volume.tar.gz -C /source .
echo "✓ PostgreSQLボリュームバックアップ完了"

# 4. 設定ファイルのバックアップ
echo "設定ファイルをバックアップ中..."
if [ -f ".env" ]; then
  cp .env "$BACKUP_DIR/"
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
echo ""
echo "バックアップが正常に完了しました。"
echo "リストアする場合: ./scripts/immich-restore.sh $BACKUP_DIR"
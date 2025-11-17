#!/bin/bash
set -e

# 環境変数を読み込む
if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

# デフォルト値の設定
DB_USERNAME="${DB_USERNAME:-immich}"
DB_DATABASE_NAME="${DB_DATABASE_NAME:-immich}"

# バックアップディレクトリの設定
BACKUP_BASE_DIR="./backups/immich"
BACKUP_DIR="$BACKUP_BASE_DIR/immich-backup-$(date +%Y%m%d_%H%M%S)"

# バックアップディレクトリを作成
mkdir -p "$BACKUP_DIR"

echo "=== Immich バックアップ開始 ==="
echo "バックアップ先: $BACKUP_DIR"
echo "データベースユーザー: $DB_USERNAME"
echo "データベース名: $DB_DATABASE_NAME"

# 1. PostgreSQLデータベースのバックアップ
echo "PostgreSQLデータベースをバックアップ中..."
docker exec -t immich-postgres pg_dumpall -c -U "$DB_USERNAME" > "$BACKUP_DIR/database.sql"
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

# 3. Redisデータのバックアップ
echo "Redisデータをバックアップ中..."
docker run --rm \
  -v immich-redis-data:/source:ro \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine tar czf /backup/redis-data.tar.gz -C /source .
echo "✓ Redisデータバックアップ完了"

# 4. PostgreSQLボリュームのバックアップ（追加の安全性のため）
echo "PostgreSQLボリュームをバックアップ中..."
docker run --rm \
  -v immich-pgdata:/source:ro \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine tar czf /backup/pgdata-volume.tar.gz -C /source .
echo "✓ PostgreSQLボリュームバックアップ完了"

# 5. MLモデルキャッシュのバックアップ（オプション - サイズが大きい可能性あり）
echo "MLモデルキャッシュをバックアップ中..."
docker run --rm \
  -v immich-ml-cache:/source:ro \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine tar czf /backup/ml-cache.tar.gz -C /source .
echo "✓ MLモデルキャッシュバックアップ完了"

# 6. 設定ファイルのバックアップ
echo "設定ファイルをバックアップ中..."
if [ -f "docker-compose.yml" ]; then
  cp docker-compose.yml "$BACKUP_DIR/"
fi

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
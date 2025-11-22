#!/bin/bash
#
# Immichリストアスクリプト
#
# 【説明】
#   immich-backup.shで作成したバックアップからImmichのデータを復元します。
#
# 【前提条件】
#   - Docker Composeでimmichが起動していること
#   - .envファイルにDB_USERNAMEとDB_DATABASE_NAMEが設定されていること
#   - バックアップディレクトリが存在すること
#
# 【使用方法】
#   ./scripts/immich-restore.sh <バックアップディレクトリ>
#
# 【使用例】
#   ./scripts/immich-restore.sh ./backups/immich/immich-backup-20240101_120000
#
# 【注意事項】
#   ⚠️ リストアを実行すると、既存のデータは完全に上書きされます
#   ⚠️ 実行前に必ず現在のデータをバックアップしてください
#   ⚠️ リストア中はImmichサービスを停止することを推奨します
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

# 引数チェック
if [ -z "$1" ]; then
  echo "使用方法: $0 <バックアップディレクトリ>"
  echo "例: $0 ./volumes/backups/immich-backup-20240101_120000"
  exit 1
fi

BACKUP_DIR="$1"

# バックアップディレクトリの存在確認
if [ ! -d "$BACKUP_DIR" ]; then
  echo "エラー: バックアップディレクトリが見つかりません: $BACKUP_DIR"
  exit 1
fi

# 必要なファイルの存在確認
echo "=== バックアップファイルの確認 ==="
MISSING_FILES=()

if [ ! -f "$BACKUP_DIR/database.sql" ]; then
  MISSING_FILES+=("database.sql")
fi

if [ ! -f "$BACKUP_DIR/immich-data.tar.gz" ] && [ ! -f "$BACKUP_DIR/pgdata-volume.tar.gz" ]; then
  echo "警告: immich-data.tar.gz が見つかりませんが、処理を続行します"
fi

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
  echo "エラー: 以下の必須ファイルが見つかりません:"
  for file in "${MISSING_FILES[@]}"; do
    echo "  - $file"
  done
  exit 1
fi

echo "✓ バックアップファイルの確認完了"
echo ""

# 確認プロンプト
echo "警告: このリストア処理により、現在のImmichデータはすべて上書きされます。"
read -p "本当に続行しますか？ (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
  echo "リストアを中止しました。"
  exit 0
fi

echo ""
echo "=== Immich リストア開始 ==="
echo "データベースユーザー: $DB_USERNAME"
echo "データベース名: $DB_DATABASE_NAME"

# 1. すべてのコンテナを停止
echo "Immichコンテナを停止中..."
docker compose stop immich immich-machine-learning immich-redis immich-postgres
echo "✓ コンテナ停止完了"

# 2. PostgreSQLコンテナのみ起動してデータベースをリストア
echo "PostgreSQLをリストア中..."
docker compose up -d immich-postgres
echo "PostgreSQLの起動を待機中..."
sleep 10

# データベースのリストア
docker exec -i immich-postgres psql -U "$DB_USERNAME" -d "$DB_DATABASE_NAME" < "$BACKUP_DIR/database.sql"
echo "✓ データベースリストア完了"

# 3. コンテナを再度停止
docker compose stop immich-postgres

# 4. Immichデータのリストア
if [ -f "$BACKUP_DIR/immich-data.tar.gz" ]; then
  echo "Immichデータをリストア中..."
  # 既存のデータディレクトリをバックアップ（念のため）
  if [ -d "./volumes/immich/data" ]; then
    mv ./volumes/immich/data "./volumes/immich/data.old.$(date +%Y%m%d_%H%M%S)"
  fi
  mkdir -p ./volumes/immich
  tar xzf "$BACKUP_DIR/immich-data.tar.gz" -C ./volumes/immich
  echo "✓ Immichデータリストア完了"
fi

# 5. PostgreSQLボリュームのリストア（database.sqlでリストアできない場合の代替）
if [ -f "$BACKUP_DIR/pgdata-volume.tar.gz" ]; then
  echo "PostgreSQLボリュームをリストア中..."
  read -p "PostgreSQLボリュームもリストアしますか？(通常は不要です) (yes/no): " RESTORE_PGVOLUME
  if [ "$RESTORE_PGVOLUME" = "yes" ]; then
    docker run --rm \
      -v immich-pgdata:/target \
      -v "$(pwd)/$BACKUP_DIR":/backup:ro \
      alpine sh -c "rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null || true && tar xzf /backup/pgdata-volume.tar.gz -C /target"
    echo "✓ PostgreSQLボリュームリストア完了"
  fi
fi

# 6. 設定ファイルのリストア（オプション）
if [ -f "$BACKUP_DIR/.env" ]; then
  echo "設定ファイル(.env)が見つかりました。"
  read -p "設定ファイルもリストアしますか？ (yes/no): " RESTORE_CONFIG
  if [ "$RESTORE_CONFIG" = "yes" ]; then
    cp "$BACKUP_DIR/.env" .env.backup.$(date +%Y%m%d_%H%M%S)
    cp "$BACKUP_DIR/.env" .env
    echo "✓ 設定ファイルリストア完了（既存の.envは.env.backupとして保存）"
  fi
fi

# 7. すべてのサービスを起動
echo "Immichサービスを起動中..."
docker compose up -d immich immich-machine-learning immich-redis immich-postgres

echo ""
echo "=== リストア完了 ==="
echo "Immichのリストアが正常に完了しました。"
echo ""
echo "サービスの状態確認:"
docker compose ps immich immich-machine-learning immich-redis immich-postgres
echo ""
echo "ログを確認する場合: docker compose logs -f immich"
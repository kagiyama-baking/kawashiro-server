# Immich バックアップ・リストア システム

このディレクトリには、Immichのデータベースと写真データをバックアップ・リストアするためのスクリプトが含まれています。

## 概要

- **バックアップ**: PostgreSQLデータベースを定期的にバックアップし、OneDriveにアップロード
- **リストア**: バックアップからデータベースを復元

## ディレクトリ構成

```
backup/
├── Dockerfile              # バックアップコンテナのイメージ定義
├── README.md              # このファイル
├── pyproject.toml         # Python依存関係
├── scripts/
│   ├── __init__.py
│   ├── backup_immich.py   # バックアップスクリプト
│   └── restore_immich.py  # リストアスクリプト
└── tests/                 # テストコード
    ├── __init__.py
    ├── test_backup_immich.py
    └── test_restore_immich.py
```

## 環境変数

バックアップ・リストアには以下の環境変数が必要です（`.env.backup`に定義）：

### 必須環境変数

- `DB_HOSTNAME`: PostgreSQLホスト名（例: `immich-postgres`）
- `DB_USERNAME`: PostgreSQLユーザー名
- `DB_PASSWORD`: PostgreSQLパスワード
- `DB_DATABASE_NAME`: データベース名（例: `immich`）
- `DJANGO_API_URL`: Django APIのURL（例: `http://django-api:8000`）
- `DJANGO_API_TOKEN`: Django APIの認証トークン
- `ONEDRIVE_BACKUP_PATH`: OneDrive上のバックアップ先パス

### オプション環境変数

- `BACKUP_DATA`: 写真データもバックアップするか（`true`/`false`、デフォルト: `false`）
- `BACKUP_RETENTION_GENERATIONS`: OneDrive上に保持するバックアップ世代数（デフォルト: `7`）
- `TZ`: タイムゾーン（例: `Asia/Tokyo`）

## バックアップ

### 手動バックアップ

```bash
# バックアップを実行（以下のコマンドはどちらも同じ動作）
docker compose -f docker-compose.backup.yml up
docker compose -f docker-compose.backup.yml run --rm backup

# ログを確認しながら実行（フォアグラウンド）
docker compose -f docker-compose.backup.yml up

# バックグラウンドで実行
docker compose -f docker-compose.backup.yml up -d

# バックグラウンド実行時のログ確認
docker compose -f docker-compose.backup.yml logs -f
```

> **注意**: 現在のDockerfileには`CMD`でバックアップスクリプトが指定されているため、
> コンテナ起動時に自動的にバックアップが1回実行されます。
> スケジューラによる定期実行機能は含まれていません。

### バックアップの内容

- **データベースバックアップ**: `immich_db_YYYYMMDD_HHMMSS.sql.gz`
  - PostgreSQLデータベースのダンプファイル（gzip圧縮）
  - メタデータ、ユーザー情報、アルバム情報などを含む

- **写真データバックアップ**（オプション、`BACKUP_DATA=true`の場合）: `immich_data_YYYYMMDD_HHMMSS.tar.gz`
  - 写真ファイルのtar.gz圧縮アーカイブ

### バックアップの保存先

1. **ローカル**: `/backup`ディレクトリ（`./volumes/backup`にマウント）
2. **OneDrive**: `ONEDRIVE_BACKUP_PATH`で指定したパス

### バックアップの世代管理

- ローカル: バックアップ完了後、全ファイルを削除
- OneDrive: `BACKUP_RETENTION_GENERATIONS`で指定した世代数を保持し、古いファイルは完全削除

## リストア

### 前提条件

⚠️ **重要**: リストアを実行する前に、以下を必ず実行してください：

1. **Immichサービスを停止**
   ```bash
   docker compose stop immich
   ```

2. **現在のデータをバックアップ**（推奨）
   ```bash
   docker compose -f docker-compose.backup.yml run --rm backup python /app/scripts/backup_immich.py
   ```

### ローカルファイルからリストア

ローカルの`/backup`ディレクトリに保存されているバックアップファイルからリストア：

```bash
# バックアップファイル一覧を確認
ls -lh volumes/backup/
# 例:
# immich_db_20250127_120000.sql.gz    (データベース)
# immich_data_20250127_120000.tar.gz  (写真データ、BACKUP_DATA=trueの場合)

# データベースのみリストア
docker compose -f docker-compose.backup.yml run --rm backup \
  python /app/scripts/restore_immich.py immich_db_20250127_120000.sql.gz

# データベースと写真データをリストア
# 注: immich_data_20250127_120000.tar.gz が同じディレクトリに存在する必要があります
docker compose -f docker-compose.backup.yml run --rm backup \
  python /app/scripts/restore_immich.py --with-data immich_db_20250127_120000.sql.gz

# または --local オプションを明示的に指定
docker compose -f docker-compose.backup.yml run --rm backup \
  python /app/scripts/restore_immich.py --local --with-data immich_db_20250127_120000.sql.gz
```

### OneDriveからリストア

OneDriveに保存されているバックアップファイルを自動的にダウンロードしてリストア：

```bash
# OneDrive上のバックアップファイル一覧を確認（Django APIを使用）
# ブラウザまたはcurlでアクセス
curl -H "Authorization: Token YOUR_TOKEN" \
  "http://localhost:8000/onedrive/list/?folder_path=/path/to/backup"
# 戻り値の例:
# - immich_db_20250127_120000.sql.gz
# - immich_data_20250127_120000.tar.gz

# データベースのみリストア
docker compose -f docker-compose.backup.yml run --rm backup \
  python /app/scripts/restore_immich.py --from-onedrive immich_db_20250127_120000.sql.gz

# データベースと写真データをリストア
# 注: OneDriveから immich_data_20250127_120000.tar.gz も自動的にダウンロードされます
docker compose -f docker-compose.backup.yml run --rm backup \
  python /app/scripts/restore_immich.py --from-onedrive --with-data immich_db_20250127_120000.sql.gz
```

### リストアプロセス

リストアスクリプトは以下の処理を実行します：

1. 環境変数の確認
2. バックアップファイルの取得（ローカルまたはOneDrive）
3. 既存のデータベース接続を切断
4. データベースを削除して再作成
5. バックアップファイルからデータをリストア
6. **（`--with-data`指定時）** 写真データファイルの取得とリストア
   - 既存の写真データを削除
   - バックアップファイルから写真データを展開
7. 一時ファイルのクリーンアップ（OneDriveからダウンロードした場合）

### 写真データのリストアについて

- `--with-data`オプションを指定すると、データベースだけでなく写真データもリストアされます
- **重要**: バックアップでは2つのファイルが作成されます
  - データベース: `immich_db_YYYYMMDD_HHMMSS.sql.gz`
  - 写真データ: `immich_data_YYYYMMDD_HHMMSS.tar.gz`（`BACKUP_DATA=true`の場合のみ）
- リストアスクリプトは、データベースファイル名から写真データファイル名を自動的に推測します
  - 例: `immich_db_20250127_120000.sql.gz` を指定すると、自動的に `immich_data_20250127_120000.tar.gz` を探します
- 写真データファイルが見つからない場合は警告が表示され、データベースのみリストアされます
- 写真データは完全に上書きされるため、リストア前に必ずバックアップを取ってください

### リストア後の手順

リストアが完了したら、Immichサービスを再起動してください：

```bash
# Immichサービスを起動
docker compose start immich

# または全サービスを再起動
docker compose restart
```

## 開発

### テストの実行

```bash
cd backup
uv run pytest tests/ -v
```

### リントとフォーマット

```bash
cd backup
uv run ruff check scripts/ tests/
uv run ruff format scripts/ tests/
```

## トラブルシューティング

### バックアップが失敗する

1. **環境変数の確認**
   ```bash
   docker compose -f docker-compose.backup.yml config
   ```

2. **ログの確認**
   ```bash
   docker compose -f docker-compose.backup.yml logs backup
   ```

3. **データベース接続の確認**
   ```bash
   docker exec backup psql -h immich-postgres -U immich -d immich -c "SELECT 1"
   ```

### リストアが失敗する

1. **Immichサービスが停止しているか確認**
   ```bash
   docker compose ps
   ```

2. **データベースへの接続を確認**
   ```bash
   docker exec backup psql -h immich-postgres -U immich -d postgres -c "SELECT 1"
   ```

3. **バックアップファイルの整合性を確認**
   ```bash
   # gzipファイルが破損していないか確認
   gunzip -t volumes/backup/immich_db_YYYYMMDD_HHMMSS.sql.gz
   ```

### OneDriveとの通信が失敗する

1. **Django APIへの接続を確認**
   ```bash
   curl -H "Authorization: Token YOUR_TOKEN" http://localhost:8000/onedrive/list/
   ```

2. **トークンの有効性を確認**
   - `.env.backup`の`DJANGO_API_TOKEN`が正しいか確認

3. **OneDriveパスの確認**
   - `ONEDRIVE_BACKUP_PATH`が正しいパスか確認

## セキュリティに関する注意事項

- `.env.backup`ファイルには機密情報（パスワード、トークンなど）が含まれるため、Gitにコミットしないでください
- バックアップファイルには個人情報が含まれる可能性があるため、適切に保護してください
- OneDriveへのアクセストークンは定期的に更新してください

## 定期バックアップの設定

cronやsystemd timerを使用して定期的にバックアップを実行できます：

### cronの例

```bash
# 毎日午前3時にバックアップを実行
0 3 * * * cd /path/to/kawashiro-server && docker compose -f docker-compose.backup.yml run --rm backup python /app/scripts/backup_immich.py
```

### systemd timerの例

timer設定とservice設定を作成してsystemdで管理することも可能です。

## ライセンス

このプロジェクトのライセンスに従います。

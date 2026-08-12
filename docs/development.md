# 開発環境ガイド

ローカルでの開発・検証環境の使い方をまとめた唯一の正（SSOT）です。テスト実行コマンドの詳細はこのファイルに集約しています。

関連ドキュメント: [初期セットアップ（管理画面）](./initial-setup.md) / [デプロイ](./deployment.md) / [sbv2_api](../sbv2_api/README.md)

## 1. 前提ツール

| ツール             | バージョン                | 用途                                                       |
| ------------------ | ------------------------- | ---------------------------------------------------------- |
| Docker Engine      | 20.10.0+                  | コンテナ実行                                               |
| Docker Compose     | v2.0.0+（`docker compose`）| サービス構成                                              |
| uv                 | 最新                      | Python 依存管理（`pip` は使わない）                        |
| Python             | 3.13（django_api）        | ホストから pytest を回す場合のみ必要                       |
| Python             | 3.10（sbv2_api）          | 同上。django_api とは別バージョン                          |
| Node.js            | 22                        | フロントエンド開発（CI・Dockerfile も 22）                 |
| corepack           | 同梱                      | pnpm のバージョン固定に使用                                |

pnpm は `frontend/package.json` の `packageManager` で **10.32.1** に固定されています。グローバルに入れるのではなく corepack 経由で使ってください。

```bash
corepack enable
cd frontend && corepack install   # packageManager の指定どおりに pnpm を用意
```

> **Note:** pnpm 11 を使うと `package.json` の `pnpm` フィールドが読まれず `onlyBuiltDependencies` が無視されるため、msw のビルドが落ちます。CI も `pnpm/action-setup` に `package_json_file: frontend/package.json` を渡してバージョンを追従させています。

## 2. 初回セットアップ

### 2.1 環境変数ファイルの作成

```bash
cp django_api/.env.sample django_api/.env
```

最低限 `SECRET_KEY` と `ENCRYPTION_KEY` を自前の値に置き換えます。各変数の意味はルート [README.md](../README.md) の「環境変数設定」を参照してください。

### 2.2 永続化ディレクトリの作成

コンテナが bind mount する 3 つのディレクトリをホスト側に用意します。存在しないまま起動すると root 所有で自動作成され、権限エラーの原因になります。

```bash
sudo mkdir -p /opt/app/django-api/staticfiles \
              /opt/app/django-api/media \
              /opt/app/sbv2-api/model_assets
sudo chown -R $USER:$USER /opt/app/
```

| パス                             | マウント先                    | 用途                             |
| -------------------------------- | ----------------------------- | -------------------------------- |
| `/opt/app/django-api/staticfiles`| `django-api`                  | `collectstatic` の出力           |
| `/opt/app/django-api/media`      | `django-api`                  | チャット履歴の TTS 音声など      |
| `/opt/app/sbv2-api/model_assets` | `sbv2-api`（読み取り専用）    | 学習済み音声モデル               |

> `celery-worker` / `celery-beat` は staticfiles と media をマウントしません。この 2 つのサービスからメディアファイルを読み書きする実装は追加しないでください。

### 2.3 起動

```bash
docker compose up -d django-api frontend
docker compose logs -f django-api
```

`django-api` の `command` が `migrate` → `collectstatic` → `runserver` を自動実行するため、初回でも手動マイグレーションは不要です。

### 2.4 動作確認

```bash
curl http://localhost:8000/health/    # Django API
curl http://localhost:3000/           # Frontend（nginx 配信）
```

管理画面へのスーパーユーザー作成と各種設定レコードの投入は [初期セットアップ](./initial-setup.md) を参照してください。

## 3. コンテナの起動パターン

### 軽量起動（日常の開発はこれ）

```bash
docker compose up -d django-api frontend
```

`depends_on` により `app-database` と `redis` も起動します。`celery-worker` / `celery-beat` は起動しません（定期タスクや HN Agent を触らない限り不要）。

### フル起動

```bash
docker compose up -d
```

`sbv2-api` のビルドで PyTorch wheel と日本語 BERT モデル（`ku-nlp/deberta-v2-large-japanese-char-wwm`）をダウンロードするため、**初回は数 GB のダウンロードと数十分**を要します。音声合成を触らない日はフル起動を避けてください。

### GPU ホスト

NVIDIA GPU 搭載ホストでは `docker-compose.gpu.yml` を重ねます（`TORCH_VARIANT=cu121` でビルドし `SBV2_DEVICE=cuda` で推論）。

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

毎回 `-f` を書くのが煩雑な場合は、リポジトリルートの `.env`（`.gitignore` 済み・ホスト固有設定）に次を書くと `docker compose up -d` だけで GPU 構成になります。

```dotenv
COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
```

## 4. バックエンドのテスト実行

### 4.1 最大の落とし穴：ホストからは DB に繋がらない

`django_api/.env` の `DB_HOST=app-database` は **コンテナネットワーク内でのみ解決可能**です。`docker-compose.yml` の `app-database` はホストへポートを公開していないため、`.env` をそのままにしてホストから pytest を実行すると DB 接続で失敗します。

対処は `DB_ENGINE` をコメントアウトすることです。`django_api/settings.py` は `DB_ENGINE` が未設定なら SQLite にフォールバックします（CI の `django-api-test` ジョブと同一構成）。

```dotenv
# django_api/.env
# DB_ENGINE=django.db.backends.postgresql
```

一時的に切り替えたいだけなら、`.env` を編集せず環境変数で空値を渡す方法もあります（`load_dotenv()` は既存の環境変数を上書きしないため）。

```bash
cd django_api && DB_ENGINE= uv run pytest tests/
```

### 4.2 正準コマンド

`django_api/pyproject.toml` の `addopts` に `--tb=short --strict-markers -n auto -m "not e2e"` が既定で入っているため、通常はこれだけで十分です。

```bash
cd django_api
uv run pytest tests/
```

`-n auto` により pytest-xdist で並列実行されます。

### 4.3 CI 相当（カバレッジ 80% 必須）

```bash
cd django_api
uv run pytest tests/ \
  --cov=user --cov=core --cov=integrations --cov=features \
  --cov-report=term-missing \
  --cov-fail-under=80
```

### 4.4 個別実行

```bash
uv run pytest tests/features/talk/ -v                      # ディレクトリ単位
uv run pytest tests/integrations/weather/test_client.py -v  # ファイル単位
uv run pytest tests/features/talk/test_services.py::test_関数名 -v
uv run pytest tests/ -m unit                                # マーカー指定
```

### 4.5 マーカー

`unit` / `integration` / `api` / `slow` / `e2e` の 5 つが定義済みですが、**`slow` と `e2e` は現時点で使用箇所が 0 件**です。`--strict-markers` が有効なため、未定義のマーカーを使うとエラーになります。追加する場合は `pyproject.toml` の `markers` にも登録してください。

テストの命名規則・ファクトリ・共通フィクスチャなどの規約は [../.claude/CLAUDE.md](../.claude/CLAUDE.md) を参照してください。

## 5. リント・フォーマット

### Python（django_api / sbv2_api）

Ruff を使います。詳しい運用は `ruff-linter` スキルに従ってください。

```bash
uv run ruff check --fix .        # リンタ（自動修正あり）
uv run ruff format .             # フォーマット適用
```

CI は `ruff check .` と `ruff format --check .` で検証します。

### フロントエンド

```bash
cd frontend
pnpm lint            # ESLint
pnpm format:check    # Prettier（CI 相当。適用は pnpm format）
pnpm type-check      # tsc --noEmit
```

## 6. フロントエンド開発

### 開発サーバー

```bash
cd frontend
pnpm install
pnpm dev             # http://localhost:5173
```

`vite.config.ts` の proxy が `/api` を `http://localhost:8000` へ転送し、パスから `/api` を除去します。バックエンドは `docker compose up -d django-api` で起動しておいてください。

### ユニットテスト（Vitest）

```bash
pnpm test       # watch モード
pnpm test:ci    # CI 相当（カバレッジ付き）
```

カバレッジの計測対象は `src/stores/**`・`src/lib/**`・`src/components/auth/**` に限定され、`src/stores/chat-store.ts` と `src/lib/pdf/pdf-worker.ts` は除外されています。閾値は lines 80%。**全ソースを計測しているわけではない**点に注意してください。

### E2E テスト（Playwright）

`e2e/` に login / media / navigation / tts の 4 本。API は `page.route` でモックするため **バックエンドの起動は不要**です。`playwright.config.ts` の `webServer` が `pnpm dev`（ポート 5173）を自動起動します。**CI では実行されません**（手動実行のみ）。

```bash
cd frontend
pnpm exec playwright install chromium   # 初回のみ
pnpm test:e2e                           # ヘッドレス
pnpm test:e2e:ui                        # UI モード
```

## 7. sbv2_api の開発

API 仕様・モデル資産の配置・CPU/GPU 切替は [../sbv2_api/README.md](../sbv2_api/README.md) を参照してください。テストは `style_bert_vits2` と `torch` をスタブ化するため、torch も学習済みモデルも不要です。

```bash
cd sbv2_api
uv sync                        # 軽量依存のみ
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format --check .
```

`server.py` はコンテナへマウントされているため、コード変更の反映に再ビルドは不要です（`docker compose restart sbv2-api` で反映）。

## 8. コンテナ統合テスト（CI）の中身

`.github/workflows/pr-checks.yml` の `container-integration-tests` ジョブは、PostgreSQL 構成での起動を検証します（ホストからの pytest とは違い、こちらは `.env.sample` をそのままコピーするので PostgreSQL を使います）。

1. `django_api/.env.sample` をコピーし、`SECRET_KEY` 等の CI 用値を追記する
2. `/opt/app/django-api/staticfiles` を作成し、`django-api` イメージをビルドする
3. `app-database` を起動して `migrate --run-syncdb` → `migrate --check`（未適用マイグレーションの検出）
4. `collectstatic --noinput --dry-run` で静的ファイル収集を確認する
5. `django-api` を起動し `/health/` の応答を最大 60 秒待ってから、`/schema/`（OpenAPI）と `/swagger/` の疎通を確認する

## 9. トラブルシューティング

### ホストから pytest すると DB 接続で失敗する

`.env` の `DB_ENGINE` が有効なままです。[4.1](#41-最大の落とし穴ホストからは-db-に繋がらない) を参照してください。

### 実行中コンテナのコードとリポジトリのブランチは別物になりうる

bind mount とブランチ切替を併用している環境では、**実行中プロセスが読み込んだコードがリポジトリのどのブランチとも一致しない**ことがあります（プロセスは起動時のコード、マウント上のファイルは切替後のコード）。「動いているからコードは正しい」と推論せず、`docker inspect` の `StartedAt`・compose ラベル・ログの出力フォーマットから実行中コードの由来を特定してから判断してください。疑わしい場合はコンテナを再作成します。

```bash
docker inspect django --format '{{.State.StartedAt}}'
docker compose up -d --force-recreate django-api
```

### 永続化ディレクトリで権限エラーが出る

`/opt/app/` 配下が root 所有になっています。[2.2](#22-永続化ディレクトリの作成) の `chown` を実行してください。

### msw のインストールでビルドが落ちる

pnpm のバージョンが 11 以上です。`corepack install` を `frontend/` で実行し、`packageManager` の指定（10.32.1）に合わせてください。

### `docker compose up -d` が GPU 構成で起動してしまう / してくれない

リポジトリルートの `.env` の `COMPOSE_FILE` を確認してください。このファイルは `.gitignore` 済みのホスト固有設定のため、マシンによって存在有無が異なります。

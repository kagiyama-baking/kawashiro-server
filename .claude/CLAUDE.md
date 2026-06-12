# CLAUDE.md

## プロジェクト概要

**kawashiro-server** は、Docker Compose で構成されたアプリケーションサーバーシステムです。Django REST Framework ベースの API サーバーを中心に、音声合成（Style-BERT-VITS2）などのサービスを統合しています。本番環境のデプロイとリバースプロキシ（Traefik）は internal.kagiyama.net リポジトリ（Ansible）が管理します。

## リポジトリ構造

```
kawashiro-server/
├── django_api/              # Django REST Framework API サーバー（メインサービス）
│   ├── core/                # ユーザー認証・コアモデル（カスタムUserモデル）
│   ├── user/                # ユーザー管理API（作成・トークン認証・更新）
│   ├── health/              # ヘルスチェック
│   ├── integrations/        # 外部サービス連携
│   │   ├── llm/             # LLM設定・クライアント（OpenAI API: チャット + Embedding）
│   │   ├── msgraph/         # Microsoft Graph API設定・クライアント
│   │   ├── onedrive/        # OneDrive連携API
│   │   ├── outlook/         # Outlook Calendar連携API
│   │   ├── tts/             # Text-to-Speech クライアント（SBV2連携）
│   │   ├── weather/         # 気象庁天気予報クライアント
│   │   ├── hn/              # Hacker News Algolia APIクライアント
│   │   ├── tavily/          # Tavily Web検索APIクライアント
│   │   └── slack/           # Slack Incoming Webhook通知クライアント
│   ├── features/            # ビジネス機能
│   │   ├── talk/            # 会話生成API（LLM + 天気 + 予定 + TTS統合）
│   │   ├── media/           # 画像処理API
│   │   └── hn_agent/        # HN監視・分析エージェント
│   ├── django_api/          # Djangoプロジェクト設定（settings.py, urls.py）
│   ├── tests/               # テストディレクトリ（pytestベース）
│   │   ├── integrations/    # 外部サービス連携テスト
│   │   ├── features/        # ビジネス機能テスト
│   │   ├── user/            # ユーザーテスト
│   │   └── health/          # ヘルスチェックテスト
│   ├── pyproject.toml       # Python依存関係・ツール設定
│   └── Dockerfile           # Python 3.13-alpine ベース
├── sbv2_api/                # Style-BERT-VITS2 音声合成サーバー（FastAPI、CPU推論）
│   ├── server.py            # APIサーバー本体
│   ├── tests/               # テスト（style_bert_vits2/torchはスタブ化）
│   ├── pyproject.toml       # テスト用依存・ツール設定
│   └── Dockerfile           # Python 3.10ベース（TORCH_VARIANTビルド引数でCPU/CUDA切替）
├── frontend/                # React SPA フロントエンド（Vite + TypeScript + Tailwind）
│   ├── src/                 # ソースコード（features/, components/, lib/ 等）
│   └── Dockerfile           # ビルド + nginx 配信
├── volumes/                 # 永続化データ（.gitkeepのみ管理）
├── docker-compose.yml       # 開発環境用
├── docker-compose.gpu.yml   # NVIDIA GPUホスト用オーバーライド（sbv2-api をCUDA化）
└── .github/workflows/       # CI/CDワークフロー
```

## 技術スタック

| カテゴリ                | 技術                                              |
| ----------------------- | ------------------------------------------------- |
| 言語                    | Python 3.13                                       |
| フレームワーク          | Django 6.0 + Django REST Framework 3.16           |
| API ドキュメント        | drf-spectacular（OpenAPI/Swagger）                |
| データベース            | PostgreSQL 17（pgvector拡張対応）                 |
| タスクキュー            | Celery + Redis（定期タスク: django-celery-beat）  |
| 認証                    | Token認証（rest_framework.authtoken）             |
| テスト                  | pytest + pytest-django + pytest-cov + pytest-mock |
| テストデータ            | factory-boy + Faker（日本語ロケール）             |
| リンター/フォーマッター | Ruff                                              |
| パッケージ管理          | uv（pip互換、高速）                               |
| コンテナ                | Docker Compose                                    |
| CI/CD                   | GitHub Actions                                    |
| セキュリティスキャン    | Trivy                                             |
| コンテナレジストリ      | GitHub Container Registry（GHCR）                 |

## 開発方針

このプロジェクトでは**テスト駆動開発（TDD）**を採用しています。すべてのコード変更は TDD サイクルに従ってください。

### TDD サイクル（Red-Green-Refactor）

#### 1. Red（失敗するテストを書く）

- 実装コードを書く**前に**、必ずテストを先に書く
- テストが失敗することを確認してから次に進む
- テストは具体的で、1 つの振る舞いのみを検証する

#### 2. Green（テストを通す最小限のコードを書く）

- テストを通すために必要な**最小限**のコードのみを実装する
- この段階では完璧なコードを目指さない
- まずは動くことを優先する

#### 3. Refactor（リファクタリング）

- テストが通った状態を維持しながらコードを改善する
- 重複を排除し、可読性を向上させる
- リファクタリング後も全テストがパスすることを確認する

### 実装手順

```
1. 要件を理解する
2. テストファイルを作成/編集する
3. 失敗するテストを書く
4. テストを実行して失敗を確認する（Red）
5. テストを通す最小限のコードを書く
6. テストを実行して成功を確認する（Green）
7. コードをリファクタリングする
8. テストを実行して成功を維持する（Refactor）
9. 次の機能へ進む（1に戻る）
```

### 禁止事項

- テストなしで実装コードを書くこと
- 複数の機能を一度にテストすること
- テストが失敗している状態で別の機能に着手すること
- リファクタリング中に新機能を追加すること

## コマンドリファレンス

### Django API テスト

```bash
# テスト実行（django_api/ ディレクトリで実行）
cd django_api

# 全テスト実行（e2eテストを除く、カバレッジ付き）
uv run pytest tests/ -v --tb=short \
  --cov=user --cov=core --cov=integrations --cov=features \
  --cov-report=term-missing -m "not e2e"

# 特定アプリのテストのみ実行
uv run pytest tests/features/talk/ -v
uv run pytest tests/integrations/weather/ -v
uv run pytest tests/user/ -v

# 特定テスト関数を実行
uv run pytest tests/features/talk/test_services.py::test_関数名 -v

# カバレッジレポート付き（CI相当）
uv run pytest tests/ -v --tb=short \
  --cov=user --cov=core --cov=integrations --cov=features \
  --cov-report=term-missing --cov-report=html \
  --cov-fail-under=80 -m "not e2e"
```

### リンター・フォーマッター（Ruff）

```bash
# django_api/ ディレクトリで実行
cd django_api

# フォーマット適用
uv run ruff format .

# フォーマット確認のみ（CI相当）
uv run ruff format --check .

# リンタ実行
uv run ruff check .

# リンタ + 自動修正
uv run ruff check --fix .
```

### Docker

```bash
# 開発環境の起動
docker compose up -d

# Django APIのみ再ビルド
docker compose build django-api

# マイグレーション実行
docker compose exec django-api python manage.py migrate

# ログ確認
docker compose logs -f django-api
```

## テスト構成

### ディレクトリ構造

```
django_api/tests/
├── conftest.py              # 共通フィクスチャ（APIClient, User, Token等）
├── fixtures/
│   └── factories.py         # factory-boy ファクトリ（UserFactory等）
├── integrations/            # 外部サービス連携テスト
│   ├── llm/                 # LLM設定・クライアントテスト
│   ├── msgraph/             # MS Graph設定・クライアントテスト
│   ├── onedrive/            # OneDriveテスト
│   ├── outlook/             # Outlookテスト
│   ├── tts/                 # TTSテスト
│   ├── weather/             # 天気予報テスト
│   ├── hn/                  # HN Algolia APIテスト
│   ├── tavily/              # Tavily APIテスト
│   └── slack/               # Slack通知テスト
├── features/                # ビジネス機能テスト
│   ├── talk/                # 会話生成テスト
│   ├── media/               # メディア処理テスト
│   └── hn_agent/            # HN Agentテスト（タスク・Agent・Orchestrator・Reporter）
├── user/                    # ユーザー管理テスト
└── health/                  # ヘルスチェックテスト
```

### テストマーカー

```python
@pytest.mark.unit         # 単体テスト（DBアクセスなし）
@pytest.mark.integration  # 統合テスト（DBアクセスあり）
@pytest.mark.api          # APIエンドポイントテスト
@pytest.mark.slow         # 実行が遅いテスト
@pytest.mark.e2e          # E2Eテスト（外部サービスアクセス、デフォルト除外）
```

### テスト命名規則

```python
def test_[テスト対象]_[条件]_[期待結果]():
    ...

# 例:
def test_user_login_with_valid_credentials_returns_token():
    ...
def test_user_login_with_invalid_password_raises_error():
    ...
```

### 良いテストの特徴

- **Fast**: 高速に実行できる
- **Independent**: 他のテストに依存しない
- **Repeatable**: 何度実行しても同じ結果
- **Self-validating**: 成功/失敗が明確
- **Timely**: 実装前に書かれている

### 共通フィクスチャ（conftest.py）

| フィクスチャ                  | 説明                               |
| ----------------------------- | ---------------------------------- |
| `api_client`                  | 未認証の APIClient                 |
| `regular_user`                | 一般ユーザー                       |
| `superuser`                   | スーパーユーザー                   |
| `auth_token`                  | 一般ユーザー用認証トークン         |
| `superuser_token`             | スーパーユーザー用認証トークン     |
| `authenticated_client`        | 認証済み APIClient                 |
| `superuser_client`            | スーパーユーザー認証済み APIClient |
| `mock_file` / `mock_pdf_file` | テスト用ファイル                   |
| `mock_ms_graph_settings`      | MS Graph設定モック                 |
| `ms_graph_client`             | OneDrive MSGraphClientモック       |

### テストファクトリ（factory-boy）

```python
from tests.fixtures.factories import UserFactory, SuperUserFactory, FileUploadFactory

user = UserFactory()                          # 一般ユーザー
admin = SuperUserFactory()                    # スーパーユーザー
users = UserFactory.create_batch_with_tokens(5)  # トークン付き5ユーザー
file = FileUploadFactory.create_text_file()   # テストファイル
```

## コーディング規約

### Ruff 設定

- **ターゲットバージョン**: Python 3.13
- **行の長さ**: 88文字
- **引用符**: ダブルクォート
- **有効なルール**: E, W, F, I, N, UP, B, C4, DJ, PIE, SIM
- **無視するルール**: DJ001（文字列フィールドのnull=True）, E501（行長制限、日本語コメント考慮）
- **除外ディレクトリ**: migrations, .venv, **pycache**

### Django アプリ構造パターン

各 Django アプリは以下のパターンに従います：

```
app_name/
├── __init__.py
├── apps.py          # アプリ設定
├── models.py        # データモデル
├── views.py         # APIビュー（DRF ViewSet/APIView）
├── serializers.py   # シリアライザ
├── urls.py          # URLルーティング
├── admin.py         # 管理画面設定
├── exceptions.py    # カスタム例外
└── migrations/      # DBマイグレーション
```

### コードスタイル

- コメントとドキュメントは**日本語**で記述
- Django モデルの `verbose_name` は日本語
- コミットメッセージは**日本語**（Conventional Commits形式: `feat:`, `fix:`, `refactor:` 等）
- `save()` メソッドでは `self.full_clean()` を呼び出してからスーパークラスの `save()` を呼ぶ

### 環境変数

Django API に必要な環境変数（`django_api/.env`）：

| 変数名            | 必須 | 説明                                               |
| ----------------- | ---- | -------------------------------------------------- |
| `SECRET_KEY`      | 必須 | Django SECRET_KEY                                  |
| `DEBUG`           | 任意 | デバッグモード（デフォルト: False）                |
| `ALLOWED_HOSTS`   | 任意 | 許可ホスト（カンマ区切り、デフォルト: localhost）  |
| `ENCRYPTION_KEY`  | 任意 | DB保存用暗号化キー                                 |
| `TTS_SERVICE_URL` | 任意 | TTSサービスURL（デフォルト: http://sbv2-api:5000） |
| `CELERY_BROKER_URL` | 任意 | Celeryブローカー（デフォルト: redis://redis:6379/0）|

> **Note:** OpenAI APIキー、Tavily APIキー、Slack Webhook URL等の機密情報はDjango管理画面（`/admin/`）からDB設定として管理。環境変数では管理しない。

## API エンドポイント

| パス           | アプリ          | 説明                                    |
| -------------- | --------------- | --------------------------------------- |
| `/admin/`      | Django Admin    | 管理画面                                |
| `/schema/`     | drf-spectacular | OpenAPIスキーマ                         |
| `/swagger/`    | drf-spectacular | Swagger UI                              |
| `/redoc/`      | drf-spectacular | ReDoc UI                                |
| `/user/`       | user            | ユーザー管理（作成/トークン/更新）      |
| `/onedrive/`   | onedrive        | OneDrive連携                            |
| `/outlook/`    | outlook         | Outlook Calendar連携                    |
| `/media/`      | media           | 画像処理                                |
| `/tts/`        | tts             | 音声合成                                |
| `/weather/`    | weather         | 気象庁天気予報                          |
| `/talk/`       | talk            | 会話生成（LLM + 天気 + 予定 + TTS統合） |
| `/hn-agent/`   | hn_agent        | HN監視・分析エージェント                |

## Docker サービス構成

| サービス        | ポート       | 説明                          |
| --------------- | ------------ | ----------------------------- |
| `django-api`    | 8000         | Django REST API               |
| `celery-worker` | —            | Celeryワーカー（バックグラウンドタスク）|
| `celery-beat`   | —            | Celery Beatスケジューラ       |
| `redis`         | 6379（内部） | Celeryブローカー              |
| `app-database`  | 5432（内部） | PostgreSQL 17（pgvector）     |
| `sbv2-api`      | 5000（内部） | Style-BERT-VITS2 音声合成（CPU推論）|
| `frontend`      | 3000         | React SPA（nginx 配信）       |

### sbv2-api の CPU / GPU 切替

- デフォルトは **CPU 推論**（PyTorch CPU版 wheel）。GPU 非搭載ホスト（Intel Mac mini 等）でもそのまま動作する
- NVIDIA GPU ホストでは `docker-compose.gpu.yml` を重ねて起動する（`TORCH_VARIANT=cu118` ビルド + `SBV2_DEVICE=cuda`）

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

- `sbv2_api/server.py` は環境変数 `SBV2_DEVICE`（デフォルト: cpu）、`SBV2_CONFIG_PATH`、`SBV2_MODEL_ASSETS_PATH`、`SBV2_BERT_MODEL_PATH` で設定可能

### sbv2-api のテスト

```bash
cd sbv2_api
uv sync                # 軽量依存のみ（style_bert_vits2/torch はテスト内でスタブ化）
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format --check .
```

## CI/CD ワークフロー

### PR Checks（`pr-checks.yml`）

`develop` ブランチへの PR 時に実行：

1. **変更検出**: `dorny/paths-filter` で変更されたサービスを検出
2. **Dockerfile セキュリティスキャン**: Trivy による設定スキャン（CRITICAL/HIGH）
3. **Django API テスト**: Ruff リンター/フォーマッター → pytest（カバレッジ 80%以上必須）
4. **SBV2 API テスト**: Ruff リンター/フォーマッター → pytest（依存スタブによる軽量テスト）
5. **コンテナ統合テスト**: Docker Compose ビルド → マイグレーション → 起動 → Django API 機能テスト

### Build & Push（`build.yml`）

`develop` ブランチへの push 時に実行：

1. 変更検出 → 対象サービスのマトリクスビルド（django-api）
2. amd64 でビルド → Trivy 脆弱性スキャン
3. マルチプラットフォーム（amd64/arm64）でビルド＆GHCR へプッシュ
4. SBOM 生成 + ビルド証明（provenance）の付与

### Release（`release.yml`）

`main` ブランチへの push 時に実行：

1. GHCR 上の staging イメージ検証
2. staging → release/latest リタグ
3. 本番サーバーへのデプロイ
4. リリースサマリー出力

本番デプロイは internal.kagiyama.net（Ansible）が担当。

### Cleanup Images（`cleanup-images.yml`）

毎週日曜 UTC 0:00 に実行。2週間以上前の古いイメージを削除（最新5つは保持）。

## Git ブランチ戦略

```
main（本番）← develop（開発）← feature/xxx, hotfix/xxx
```

- `feature/*`: 機能開発ブランチ（develop へ PR）
- `hotfix/*`: 緊急修正ブランチ（develop へ PR）
- `develop`: 開発統合ブランチ（main へ PR でリリース）
- `main`: 本番ブランチ（push でリリースタグ付け、デプロイは Ansible が担当）

## レビュー規約

レビューコメントには以下の接頭辞を使用：

| 接頭辞   | 意味                     |
| -------- | ------------------------ |
| `[must]` | 必ず変更が必要           |
| `[imo]`  | 意見（修正必須ではない） |
| `[nits]` | 些細な指摘               |
| `[ask]`  | 質問                     |
| `[fyi]`  | 参考情報                 |

## 確認事項

コードを提出する前に以下を確認：

- [ ] すべてのテストがパスしている
- [ ] 新機能には対応するテストがある
- [ ] テストカバレッジが低下していない
- [ ] テストカバレッジが 80%以上である
- [ ] テストコードも適切にリファクタリングされている
- [ ] Ruff リンター/フォーマッターがパスしている
- [ ] コミットメッセージが日本語で Conventional Commits 形式に従っている

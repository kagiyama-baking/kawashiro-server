# CLAUDE.md

## プロジェクト概要

**kawashiro-server** は、Docker Compose で構成されたホームサーバーシステムです。Django REST Framework ベースの API サーバーを中心に、写真管理（Immich）、音声合成（Style-BERT-VITS2）、リバースプロキシ（Nginx）などの複数サービスを統合しています。

## リポジトリ構造

```
kawashiro-server/
├── django_api/          # Django REST Framework API サーバー（メインサービス）
│   ├── core/            # ユーザー認証・コアモデル（カスタムUserモデル）
│   ├── user/            # ユーザー管理API（作成・トークン認証・更新）
│   ├── greeting/        # 挨拶生成API（LLM + 天気 + 予定 + TTS統合）
│   ├── weather/         # 気象庁天気予報クライアント
│   ├── tts/             # Text-to-Speech クライアント（SBV2連携）
│   ├── media/           # 画像処理API
│   ├── onedrive/        # OneDrive連携API
│   ├── outlook/         # Outlook Calendar連携API
│   ├── llm_client/      # LLMクライアント（OpenAI API）
│   ├── llm_config/      # LLM設定管理
│   ├── msgraph_client/  # Microsoft Graph APIクライアント
│   ├── msgraph_config/  # Microsoft Graph設定管理
│   ├── django_api/      # Djangoプロジェクト設定（settings.py, urls.py）
│   ├── tests/           # テストディレクトリ（pytestベース）
│   ├── pyproject.toml   # Python依存関係・ツール設定
│   └── Dockerfile       # Python 3.13-alpine ベース
├── reverse_proxy/       # Nginx リバースプロキシ
├── sbv2_api/            # Style-BERT-VITS2 音声合成サーバー（FastAPI）
├── backup/              # バックアップスクリプト（Django + Immich）
├── volumes/             # 永続化データ（.gitkeepのみ管理）
├── docker-compose.yml       # 開発環境用
├── docker-compose-prod.yml  # 本番環境用
└── .github/workflows/       # CI/CDワークフロー
```

## 技術スタック

| カテゴリ | 技術 |
|---------|------|
| 言語 | Python 3.13 |
| フレームワーク | Django 6.0 + Django REST Framework 3.16 |
| API ドキュメント | drf-spectacular（OpenAPI/Swagger） |
| データベース | SQLite（開発）/ 永続化ボリューム |
| 認証 | Token認証（rest_framework.authtoken） |
| テスト | pytest + pytest-django + pytest-cov + pytest-mock |
| テストデータ | factory-boy + Faker（日本語ロケール） |
| リンター/フォーマッター | Ruff |
| パッケージ管理 | uv（pip互換、高速） |
| コンテナ | Docker Compose |
| CI/CD | GitHub Actions |
| セキュリティスキャン | Trivy |
| コンテナレジストリ | GitHub Container Registry（GHCR） |

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
  --cov=user --cov=onedrive --cov=outlook --cov=core \
  --cov-report=term-missing -m "not e2e"

# 特定アプリのテストのみ実行
uv run pytest tests/greeting/ -v
uv run pytest tests/weather/ -v
uv run pytest tests/user/ -v

# 特定テスト関数を実行
uv run pytest tests/greeting/test_services.py::test_関数名 -v

# カバレッジレポート付き（CI相当）
uv run pytest tests/ -v --tb=short \
  --cov=user --cov=onedrive --cov=outlook --cov=core \
  --cov-report=term-missing --cov-report=html \
  --cov-fail-under=80 -m "not e2e"
```

### Backup テスト

```bash
# backup/ ディレクトリで実行
cd backup
uv run pytest tests/ -v --tb=short \
  --cov=scripts --cov-report=term-missing
```

### リンター・フォーマッター（Ruff）

```bash
# django_api/ または backup/ ディレクトリで実行
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

# 本番環境の起動
docker compose -f docker-compose-prod.yml up -d

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
├── greeting/                # 挨拶機能テスト
│   ├── test_admin.py
│   ├── test_holiday_client.py
│   ├── test_models.py
│   ├── test_serializers.py
│   ├── test_services.py
│   └── test_views.py
├── llm_client/              # LLMクライアントテスト
├── media/                   # メディア処理テスト
├── msgraph_client/          # MS Graph クライアントテスト
├── msgraph_config/          # MS Graph 設定テスト
├── onedrive/                # OneDrive テスト
├── outlook/                 # Outlook テスト
├── tts/                     # TTS テスト
├── user/                    # ユーザー管理テスト
└── weather/                 # 天気予報テスト
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

| フィクスチャ | 説明 |
|-------------|------|
| `api_client` | 未認証の APIClient |
| `regular_user` | 一般ユーザー |
| `superuser` | スーパーユーザー |
| `auth_token` | 一般ユーザー用認証トークン |
| `superuser_token` | スーパーユーザー用認証トークン |
| `authenticated_client` | 認証済み APIClient |
| `superuser_client` | スーパーユーザー認証済み APIClient |
| `mock_file` / `mock_pdf_file` | テスト用ファイル |
| `mock_ms_graph_settings` | MS Graph設定モック |
| `ms_graph_client` | OneDrive MSGraphClientモック |

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
- **除外ディレクトリ**: migrations, .venv, __pycache__

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

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `SECRET_KEY` | 必須 | Django SECRET_KEY |
| `DEBUG` | 任意 | デバッグモード（デフォルト: False） |
| `ALLOWED_HOSTS` | 任意 | 許可ホスト（カンマ区切り、デフォルト: localhost） |
| `ENCRYPTION_KEY` | 任意 | DB保存用暗号化キー |
| `OPENAI_API_KEY` | 任意 | OpenAI API キー |
| `TTS_SERVICE_URL` | 任意 | TTSサービスURL（デフォルト: http://sbv2-api:5000） |

## API エンドポイント

| パス | アプリ | 説明 |
|------|--------|------|
| `/admin/` | Django Admin | 管理画面 |
| `/schema/` | drf-spectacular | OpenAPIスキーマ |
| `/swagger/` | drf-spectacular | Swagger UI |
| `/redoc/` | drf-spectacular | ReDoc UI |
| `/user/` | user | ユーザー管理（作成/トークン/更新） |
| `/onedrive/` | onedrive | OneDrive連携 |
| `/outlook/` | outlook | Outlook Calendar連携 |
| `/media/` | media | 画像処理 |
| `/tts/` | tts | 音声合成 |
| `/weather/` | weather | 気象庁天気予報 |
| `/greeting/` | greeting | 挨拶生成（LLM + 天気 + 予定 + TTS統合） |

## Docker サービス構成

| サービス | ポート | 説明 |
|---------|--------|------|
| `reverse-proxy` | 80 | Nginx リバースプロキシ |
| `django-api` | 8000 | Django REST API |
| `immich` | 2283 | Immich 写真管理 |
| `immich-machine-learning` | - | Immich ML |
| `immich-redis` | 6379 | Redis（Immich用） |
| `immich-postgres` | 5432 | PostgreSQL（Immich用） |
| `sbv2-api` | 5000（内部） | Style-BERT-VITS2 音声合成 |

## CI/CD ワークフロー

### PR Checks（`pr-checks.yml`）

`develop` ブランチへの PR 時に実行：

1. **変更検出**: `dorny/paths-filter` で変更されたサービスを検出
2. **Dockerfile セキュリティスキャン**: Trivy による設定スキャン（CRITICAL/HIGH）
3. **Django API テスト**: Ruff リンター/フォーマッター → pytest（カバレッジ 80%以上必須）
4. **Backup テスト**: Ruff → pytest（カバレッジ 80%以上必須）
5. **コンテナ統合テスト**: Docker Compose ビルド → Nginx構文チェック → マイグレーション → 起動 → 機能テスト

### Build & Push（`build.yml`）

`develop` ブランチへの push 時に実行：

1. 変更検出 → 対象サービスのマトリクスビルド
2. amd64 でビルド → Trivy 脆弱性スキャン
3. マルチプラットフォーム（amd64/arm64）でビルド＆GHCR へプッシュ
4. SBOM 生成 + ビルド証明（provenance）の付与

### Deploy（`deploy.yml`）

`main` ブランチへの push 時に実行：

1. GHCR 上のイメージ検証
2. staging → release/latest タグ付け
3. Tailscale VPN 経由で本番サーバーに SSH デプロイ

### Security Scan（`security-scan.yml`）

毎日 JST 0:00 に実行。GHCR 上の release イメージを Trivy でスキャン。

### Cleanup Images（`cleanup-images.yml`）

毎週日曜 UTC 0:00 に実行。2週間以上前の古いイメージを削除（最新5つは保持）。

## Git ブランチ戦略

```
main（本番）← develop（開発）← feature/xxx, hotfix/xxx
```

- `feature/*`: 機能開発ブランチ（develop へ PR）
- `hotfix/*`: 緊急修正ブランチ（develop へ PR）
- `develop`: 開発統合ブランチ（main へ PR でリリース）
- `main`: 本番ブランチ（push でデプロイ）

## レビュー規約

レビューコメントには以下の接頭辞を使用：

| 接頭辞 | 意味 |
|--------|------|
| `[must]` | 必ず変更が必要 |
| `[imo]` | 意見（修正必須ではない） |
| `[nits]` | 些細な指摘 |
| `[ask]` | 質問 |
| `[fyi]` | 参考情報 |

## 確認事項

コードを提出する前に以下を確認：

- [ ] すべてのテストがパスしている
- [ ] 新機能には対応するテストがある
- [ ] テストカバレッジが低下していない
- [ ] テストカバレッジが 80%以上である
- [ ] テストコードも適切にリファクタリングされている
- [ ] Ruff リンター/フォーマッターがパスしている
- [ ] コミットメッセージが日本語で Conventional Commits 形式に従っている

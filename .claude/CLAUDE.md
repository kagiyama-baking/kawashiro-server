# CLAUDE.md

## プロジェクト概要

**kawashiro-server** は、Docker Compose で構成されたアプリケーションサーバーシステムです。Django REST Framework ベースの API サーバーを中心に、音声合成（Style-BERT-VITS2）、React SPA フロントエンドを統合しています。LLM 呼び出しは LiteLLM Proxy 経由でプロバイダー非依存、観測とプロンプト管理は Langfuse に集約しています。

本番運用の分担: ホスト構築・Traefik・本番 compose/.env の配置は internal.kagiyama.net（Ansible）、イメージビルドと本番コンテナの入れ替えは GitHub Actions（詳細は `docs/deployment.md`）。

## リポジトリ構造

```
kawashiro-server/
├── django_api/              # Django REST Framework API サーバー（メインサービス）
│   ├── core/                # カスタムUserモデル・Fernet暗号化・admin並び順制御
│   ├── user/                # ユーザー管理API（作成・トークン認証・更新）
│   ├── health/              # ヘルスチェック（ミドルウェア方式、ALLOWED_HOSTS検証前に応答）
│   ├── integrations/        # 外部サービス連携
│   │   ├── llm/             # LiteLLM Proxy経由のLLMクライアント・接続設定
│   │   ├── langfuse/        # Langfuseプロンプト参照（LangfusePromptRef / resolve_prompt）
│   │   ├── msgraph/         # Microsoft Graph API設定・クライアント（証明書認証）
│   │   ├── onedrive/        # OneDrive連携API
│   │   ├── outlook/         # Outlook Calendar連携API
│   │   ├── tts/             # Text-to-Speech クライアント（SBV2連携）
│   │   ├── weather/         # 気象庁天気予報クライアント
│   │   ├── hn/              # Hacker News Algolia APIクライアント
│   │   ├── tavily/          # Tavily Web検索APIクライアント
│   │   └── slack/           # Slack Incoming Webhook通知クライアント
│   ├── features/            # ビジネス機能
│   │   ├── talk/            # 会話生成API + チャット履歴セッション
│   │   ├── media/           # 画像変換・ZIP→PDF
│   │   └── hn_agent/        # HN監視・分析エージェント（LangGraph ReAct）
│   ├── django_api/          # Djangoプロジェクト設定（settings.py, urls.py, celery.py）
│   ├── tests/               # テストディレクトリ（pytestベース）
│   ├── pyproject.toml       # Python依存関係・ツール設定
│   └── Dockerfile           # Python 3.13-alpine ベース
├── sbv2_api/                # Style-BERT-VITS2 音声合成サーバー（FastAPI）
├── frontend/                # React SPA（Vite + TypeScript + Tailwind、nginx配信）
├── docs/                    # 横断運用ガイド（development / deployment / initial-setup）
├── docker-compose.yml       # 開発環境用
├── docker-compose.gpu.yml   # NVIDIA GPUホスト用オーバーレイ（sbv2-api をCUDA化）
├── secrets/                 # ローカル専用の鍵置き場（Git追跡外・compose未マウント）
└── .github/workflows/       # CI/CD（build / release / pr-checks / security-scan / cleanup-images）
```

ホスト側の永続ディレクトリは `/opt/app/django-api/{staticfiles,media}` と `/opt/app/sbv2-api/model_assets` の 3 つ（ルート README 参照）。

## ドキュメントマップとドキュメント更新規約

### 単一ソース原則（SSOT）

同じ事実を複数のドキュメントに書かない。各事実には「正」となるファイルが 1 つだけあり、他のファイルからは相対リンクで参照する。既存の記述を見つけたらコピーせずリンクすること。唯一の例外はテスト・リントの最短コマンド（本ファイルと `docs/development.md` の 2 面持ち。変更時は両方を更新する）。

### ドキュメントマップ（何がどこに書いてあるか）

| 知りたいこと | 正となるファイル |
|---|---|
| 全体概要・クイックスタート・環境変数表・コンテナ/ポート表・永続ディレクトリ | `README.md` |
| ローカル開発・テスト実行・SQLite フォールバック等の落とし穴 | `docs/development.md` |
| CI/CD 詳細・デプロイ・Secrets・タグ運用・ロールバック | `docs/deployment.md` |
| 初期セットアップ（createsuperuser → admin 投入順 → 定期タスク登録） | `docs/initial-setup.md` |
| API 一覧（アプリ × エンドポイント）・管理画面ガイド | `django_api/README.md` |
| LLM/LiteLLM/Langfuse 3 レイヤ・admin 設定モデル・プロンプト命名規約 | `django_api/integrations/llm/README.md` |
| Talk・チャットセッション仕様・プレースホルダー | `django_api/features/talk/README.md` |
| メディア変換の制限値 | `django_api/features/media/README.md` |
| HN Agent アーキテクチャ・プロンプト変数・Celery タスク | `django_api/features/hn_agent/README.md` |
| 気象庁天気予報クライアント | `django_api/integrations/weather/README.md` |
| 音声合成 API・モデル配置・CPU/GPU 切替 | `sbv2_api/README.md` |
| フロントエンド画面・開発コマンド | `frontend/README.md` |
| テスト規約（マーカー・フィクスチャ・命名） | 本ファイル |

### 更新ルール

- コード変更をコミットする前に **docs-sync スキル**（`.claude/skills/docs-sync/`）の対応マップで更新要否を確認する
- ドキュメント更新は対応するコード変更と同じブランチ（可能なら同じコミット）に含める
- 新しい Django アプリ・画面・ワークフロー・環境変数を追加したら、上のマップ・該当 README・`django_api/.env.sample` を同時に更新する
- ドキュメントを新設・移動したら、上のマップ／ルート README のドキュメントマップ／docs-sync の対応マップも更新する

## 技術スタック

| カテゴリ                | 技術                                              |
| ----------------------- | ------------------------------------------------- |
| 言語                    | Python 3.13                                       |
| フレームワーク          | Django 6 + Django REST Framework 3.16             |
| API ドキュメント        | drf-spectacular（OpenAPI/Swagger）                |
| データベース            | PostgreSQL 17                                     |
| タスクキュー            | Celery + Redis（定期タスク: django-celery-beat）  |
| LLM ゲートウェイ        | LiteLLM Proxy（OpenAI 互換・プロバイダー非依存）  |
| LLMOps                  | Langfuse（トレース・プロンプト管理）+ LangGraph   |
| 認証                    | Token認証（rest_framework.authtoken）             |
| テスト                  | pytest + pytest-django + pytest-cov + pytest-mock + pytest-xdist |
| テストデータ            | factory-boy + Faker（日本語ロケール）             |
| リンター/フォーマッター | Ruff                                              |
| パッケージ管理          | uv（Python）/ pnpm（frontend、corepack 固定）     |
| コンテナ                | Docker Compose                                    |
| CI/CD                   | GitHub Actions + Trivy + GHCR                     |

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

### 禁止事項

- テストなしで実装コードを書くこと
- 複数の機能を一度にテストすること
- テストが失敗している状態で別の機能に着手すること
- リファクタリング中に新機能を追加すること

## コマンドリファレンス

### Django API テスト（`django_api/` で実行）

```bash
# 通常実行（--tb=short / -n auto / -m "not e2e" は addopts で設定済み）
uv run pytest tests/

# CI 相当（カバレッジ 80% 必須）
uv run pytest tests/ \
  --cov=user --cov=core --cov=integrations --cov=features \
  --cov-report=term-missing --cov-fail-under=80

# 個別実行
uv run pytest tests/features/talk/ -v
uv run pytest tests/features/talk/test_services.py::test_関数名 -v
```

ホストから実行する場合は `.env` の `DB_ENGINE` を無効化して SQLite フォールバックを使う（詳細・落とし穴は `docs/development.md`）。

### リンター・フォーマッター

Ruff を使用。ワークフローは `ruff-linter` スキルに従うこと（`uv run ruff format .` → `uv run ruff check --fix .` → `uv run ruff check .`）。

### Docker

```bash
docker compose up -d django-api frontend   # 軽量起動（推奨。sbv2 込みのフル起動は重い）
docker compose build django-api            # 再ビルド
docker compose logs -f django-api          # ログ確認
docker compose exec django-api python manage.py migrate   # 手動マイグレーション（通常は起動時に自動実行）
```

サービス一覧・ポートはルート `README.md`、sbv2 の CPU/GPU 切替は `sbv2_api/README.md` を参照。

## テスト構成

### ディレクトリ構造

```
django_api/tests/
├── conftest.py              # 共通フィクスチャ（APIClient, User, Token等）
├── fixtures/
│   └── factories.py         # factory-boy ファクトリ（UserFactory等）
├── core/                    # admin並び順等のコアテスト
├── integrations/            # 外部サービス連携テスト
│   ├── llm/ langfuse/ msgraph/ onedrive/ outlook/ tts/
│   └── weather/ hn/ tavily/ slack/
├── features/                # ビジネス機能テスト
│   ├── talk/ media/ hn_agent/
├── user/                    # ユーザー管理テスト
└── health/                  # ヘルスチェックテスト
```

### テストマーカー

```python
@pytest.mark.unit         # 単体テスト（DBアクセスなし）
@pytest.mark.integration  # 統合テスト（DBアクセスあり）
@pytest.mark.api          # APIエンドポイントテスト
@pytest.mark.slow         # 実行が遅いテスト（現在使用 0 件）
@pytest.mark.e2e          # E2Eテスト（現在使用 0 件。addopts で常時除外）
```

`--strict-markers` が有効。マーカーを追加する場合は `pyproject.toml` の `markers` にも登録すること。

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
- コミットメッセージは**日本語**（Conventional Commits形式。`commit-message-rules` スキル参照）
- `save()` メソッドでは `self.full_clean()` を呼び出してからスーパークラスの `save()` を呼ぶ

### 環境変数・機密情報

環境変数の一覧と説明はルート `README.md` の「環境変数設定」が正（サンプルは `django_api/.env.sample`）。

> **Note:** OpenAI / Bedrock 等のプロバイダー側 API キーは LiteLLM Proxy 側で管理する。Django が持つのは LiteLLM Virtual Key（admin で DB 暗号化保存）と、そのフォールバックの `LITELLM_MASTER_KEY`（環境変数）のみ。Slack Webhook・Tavily キー・MS Graph 秘密鍵は admin から DB 暗号化保存で管理する（環境変数では管理しない）。

## API エンドポイント

アプリ × エンドポイントの一覧は `django_api/README.md` の「機能一覧」が正。API 仕様の確認は `http://localhost:8000/swagger/` を参照。

## CI/CD ワークフロー（5本）

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `pr-checks.yml` | develop 宛 PR | 変更検出 → Dockerfile Trivy / Django テスト / SBV2 テスト / frontend 静的チェック+テスト / コンテナ統合テスト の 7 ジョブ |
| `build.yml` | develop push | django-api + frontend をビルド → Trivy → multi-arch で GHCR push（`sha-<short>` + `staging`）→ SBOM/provenance |
| `release.yml` | main push | `staging` の検証 → `release`/`latest` リタグ → **Tailscale+SSH で本番コンテナ入れ替え** |
| `security-scan.yml` | 毎日 JST 0:00 | `:release` イメージを Trivy スキャン → Security タブへ SARIF |
| `cleanup-images.yml` | 毎週日曜 | 2 週間超の古いイメージを削除（最新 5 件と latest/release/staging は保持） |

各ジョブの詳細・必要な Secrets・タグ運用・ロールバック手順は `docs/deployment.md` が正。

## Git ブランチ戦略

```
main（本番）← develop（開発）← feature/xxx, bugfix/xxx, hotfix/xxx
```

- `feature/*` / `bugfix/*` / `hotfix/*`: 作業ブランチ（develop へ PR）
- `develop`: 開発統合ブランチ（main へ PR でリリース）
- `main`: 本番ブランチ（push で release リタグ + 自動デプロイ）

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
- [ ] **docs-sync スキルでドキュメント更新の要否を確認した**

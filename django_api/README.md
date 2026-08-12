# Django API

REST API で複数の機能を提供するバックエンドサーバです。LLM 呼び出しは LiteLLM Proxy に集約し、観測とプロンプト管理は Langfuse に統一しています。

## 機能一覧

### API を公開するアプリ

| アプリ | エンドポイント | 説明 | 詳細 |
|---|---|---|---|
| `user` | `/user/` | ユーザー認証・管理（作成は superuser のみ / トークン発行 / 更新） | — |
| `health` | `/health/` | ヘルスチェック。ミドルウェア方式のため `ALLOWED_HOSTS` 検証前に `{"status": "ok"}` を返す | — |
| `integrations.onedrive` | `/onedrive/` | OneDrive ファイル連携（アップロード / 一覧 / 削除 / ダウンロード / 分割アップロード） | — |
| `integrations.outlook` | `/outlook/` | Outlook Calendar 予定取得 | — |
| `integrations.tts` | `/tts/` | テキスト読み上げ（Style-BERT-VITS2 プロキシ） | [sbv2_api/README.md](../sbv2_api/README.md) |
| `integrations.weather` | `/weather/` | 気象庁天気予報 | [README](integrations/weather/README.md) |
| `features.media` | `/media/` | 画像変換・ZIP→PDF（制限値あり） | [README](features/media/README.md) |
| `features.talk` | `/talk/` | 会話生成 + チャット履歴セッション + 日時情報（`/talk/datetime/`） | [README](features/talk/README.md) |
| `features.hn_agent` | `/hn-agent/` | HackerNews Agent（監視・調査・辛口分析・セキュリティ対応指針。superuser のみ） | [README](features/hn_agent/README.md) |

### 裏方のアプリ（URL なし）

| アプリ | 説明 | 詳細 |
|---|---|---|
| `core` | カスタム `User` モデル（email ログイン）・Fernet 暗号化ユーティリティ・admin 並び順制御 | — |
| `integrations.llm` | LiteLLM Proxy 経由の LLM クライアントと接続設定（`LLMProviderConfig` / `LLMServiceConfig`） | [README](integrations/llm/README.md) |
| `integrations.langfuse` | Langfuse プロンプト参照（`LangfusePromptRef` / `resolve_prompt`） | [README](integrations/llm/README.md) |
| `integrations.msgraph` | Microsoft Graph の証明書認証設定・クライアント（onedrive / outlook が利用） | — |
| `integrations.hn` | Hacker News Algolia API クライアント（hn_agent が利用。API キー不要のため設定モデルなし） | — |
| `integrations.tavily` | Tavily Web 検索クライアント（hn_agent が利用。未設定でもエージェントは検索なしで継続） | — |
| `integrations.slack` | Slack Incoming Webhook 通知（hn_agent の Reporter が利用） | — |

## アーキテクチャの肝

LLM 周辺は「LLM 接続 / プロンプト管理 / 機能設定」の 3 レイヤに分離しており、モデル差し替えもプロンプト改修も Django の再デプロイなしで行えます。責務表・admin と外部サービスの対応図・プロンプト命名規約は [integrations/llm/README.md](integrations/llm/README.md) を参照してください。

## セットアップ

```bash
cp .env.sample .env    # 変数の意味はルート README の「環境変数設定」を参照
```

```bash
# Docker（推奨。migrate と collectstatic は起動コマンドで自動実行）
docker compose up -d django-api

# ホストで直接動かす場合
uv run ./manage.py migrate
uv run ./manage.py createsuperuser
uv run ./manage.py runserver
```

初回はスーパーユーザー作成後に管理画面での設定投入が必要です。投入順序は [docs/initial-setup.md](../docs/initial-setup.md) にまとめています。ホストから pytest を実行する際の DB 設定は [docs/development.md](../docs/development.md) を参照してください。

## 管理画面での設定

Django 管理画面（`http://localhost:8000/admin/`）は 3 グループに整列されています（`core/apps.py` の `ADMIN_APP_ORDER`）。

### 1. システム設定

`Core`（ユーザー）/ `認証と認可` / `認証トークン`

### 2. 外部サービス設定

#### Microsoft 365（OneDrive / Outlook 機能）

`Microsoft Graph API 設定` から登録します。有効にできるのは 1 件のみです。

| 項目 | 説明 |
|---|---|
| テナント ID | Azure AD テナント ID |
| クライアント ID | Azure AD アプリケーション ID |
| 証明書サムプリント | 証明書のサムプリント |
| 秘密鍵 | PEM 形式（暗号化保存。空のまま保存すると既存値を保持） |
| 対象ユーザー | アクセス対象のメールアドレス |

#### Slack

Incoming Webhook URL（暗号化保存）。HN Agent のレポート送信先です。未設定でも Agent は動作し、通知だけスキップされます。

#### Tavily

Tavily Web 検索の API キー（暗号化保存）とタイムアウト（既定 30 秒）。

#### Celery（定期タスク）

`django-celery-beat` の定期タスクスケジューラ。HN Agent のポーリング（`hn_agent.poll_front_page` 等）はここで登録・有効化します。登録手順と注意点（`HNAgentConfig` のポーリング間隔は実行スケジュールを制御しない）は [docs/initial-setup.md](../docs/initial-setup.md) を参照してください。

### 3. AI ツール設定

| 管理画面 | 内容 | 詳細 |
|---|---|---|
| LLM設定 / LLMサービス設定 | モデルエイリアス + Virtual Key、サービスへの割り当て | [integrations/llm/README.md](integrations/llm/README.md) |
| Langfuseプロンプト参照 | Langfuse プロンプトのマッピング + フォールバック（HN 用 8 本は migration で自動投入、**Talk 用は手動作成**） | [integrations/llm/README.md](integrations/llm/README.md) |
| HackerNews Agent設定 | 閾値・ポーリング・プロンプト 8 本の割り当て | [features/hn_agent/README.md](features/hn_agent/README.md) |
| 会話生成設定（TalkConfig） | プリセットごとの動作パラメータ + プロンプト 2 本 + TTS | [features/talk/README.md](features/talk/README.md) |
| HNスレッド / チャットセッション | 収集データ・会話履歴の閲覧と削除 | — |

## テストの実行

```bash
uv run pytest tests/    # オプション（-n auto, -m "not e2e" 等）は pyproject.toml の addopts で設定済み
```

CI 相当のカバレッジ付き実行、ホスト実行時の DB フォールバック、マーカー一覧は [docs/development.md](../docs/development.md) を参照してください。

## API ドキュメント

| UI | パス |
|---|---|
| Swagger UI | `http://localhost:8000/swagger/` |
| ReDoc | `http://localhost:8000/redoc/` |
| OpenAPI スキーマ | `http://localhost:8000/schema/` |

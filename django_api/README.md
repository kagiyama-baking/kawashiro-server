# Django API

REST API で複数の機能を提供するバックエンドサーバです。

## 機能一覧

| アプリ   | エンドポイント | 説明                                                   |
| -------- | -------------- | ------------------------------------------------------ |
| user     | `/user/`       | ユーザー認証・管理                                     |
| onedrive | `/onedrive/`   | OneDrive ファイルアップロード・管理                    |
| outlook  | `/outlook/`    | Outlook Calendar 予定取得                              |
| media    | `/media/`      | メディアファイル管理（画像変換・ZIP→PDF）              |
| tts      | `/tts/`        | テキスト読み上げ（Style-BERT-VITS2 プロキシ）          |
| weather  | `/weather/`    | 気象庁天気予報                                         |
| talk     | `/talk/`       | 会話生成（設定ベースの AI 会話生成・TTS 対応）         |
| hn_agent | `/hn-agent/`   | HN監視・分析エージェント（Watcher・調査・結果閲覧）    |

## セットアップ

### 1. 環境変数の設定

`.env.sample` を参考に `.env` ファイルを作成してください：

```bash
cp .env.sample .env
```

```env
# Django設定
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# データベース設定（PostgreSQL）
DB_ENGINE=django.db.backends.postgresql
DB_NAME=kawashiro
DB_USER=kawashiro
DB_PASSWORD=kawashiro-dev
DB_HOST=app-database
DB_PORT=5432

# 暗号化キー（データベースに保存する機密情報の暗号化に使用）
ENCRYPTION_KEY=your-encryption-key

# Style-BERT-VITS2 API（音声合成機能）
TTS_SERVICE_URL=http://sbv2-api:5000
```

> **Note:** OpenAI APIキー、Tavily APIキー、Slack Webhook URL等の機密情報はDjango管理画面（`/admin/`）から設定します。環境変数では管理しません。

### 2. マイグレーションの実行

```bash
uv run ./manage.py migrate
```

### 3. 管理ユーザーの作成

```bash
uv run ./manage.py createsuperuser
```

### 4. サーバーの起動

```bash
# 開発環境
uv run ./manage.py runserver

# 本番環境（Docker）
docker compose up -d django-api
```

## 管理画面での設定

Django 管理画面（`http://localhost:8000/admin/`）で以下の設定を行います。

### Microsoft Graph API 設定（OneDrive/Outlook 機能）

「MSGRAPH CONFIG」から以下を設定：

| 項目               | 説明                                       |
| ------------------ | ------------------------------------------ |
| テナントID         | Azure AD テナント ID                       |
| クライアントID     | Azure AD アプリケーション ID               |
| 証明書サムプリント | 証明書のサムプリント                       |
| 秘密鍵             | PEM 形式の秘密鍵（暗号化されて DB に保存） |
| 対象ユーザー       | アクセス対象のユーザーメールアドレス       |

### 会話生成設定（Talk 機能）

「会話生成」→「会話生成設定」から複数の設定を登録できます：

| 項目               | 説明                                               |
| ------------------ | -------------------------------------------------- |
| 設定名             | API 呼び出し時の識別子（例: `morning`, `evening`） |
| 表示名             | 管理画面での表示名                                 |
| 天気情報を使用     | `{{weather}}` プレースホルダーを有効化             |
| 予定情報を使用     | `{{events}}` プレースホルダーを有効化              |
| 日時情報を使用     | `{{datetime}}` プレースホルダーを有効化            |
| 予報区コード       | 6 桁の数字（天気使用時のみ必須、例: `130010`）     |
| システムプロンプト | AI のキャラクター設定                              |
| TTS 有効           | 音声合成を有効にするか                             |
| TTS 設定           | モデル名、スタイル、速度など                       |

#### API 呼び出し例

```bash
# 設定一覧を取得
curl http://localhost:8000/talk/configs/ \
  -H "Authorization: Token YOUR_TOKEN"

# 会話生成
curl -X POST http://localhost:8000/talk/synthesize/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_name": "morning",
    "user_prompt": "{{datetime}}を踏まえて挨拶してください"
  }'
```

#### プレースホルダー

| プレースホルダー | 内容                 | 設定で有効化が必要 |
| ---------------- | -------------------- | ------------------ |
| `{{datetime}}`   | 日時・曜日・祝日情報 | 日時情報を使用     |
| `{{weather}}`    | 天気予報データ       | 天気情報を使用     |
| `{{events}}`     | 本日の予定データ     | 予定情報を使用     |

### OpenAI API 設定（LLM テキスト生成・Embedding）

「OpenAI API設定」から以下を設定：

| 項目              | 説明                                                    |
| ----------------- | ------------------------------------------------------- |
| 設定名            | この設定を識別するための名前                            |
| 有効              | この設定を有効にする（1つだけ有効可）                   |
| チャットモデル    | チャット補完に使用するモデル（例: `gpt-4o-mini`）       |
| Embeddingモデル   | Embedding生成に使用するモデル（例: `text-embedding-3-small`）|
| タイムアウト      | APIリクエストのタイムアウト秒数                          |
| APIキー           | OpenAI APIキー（暗号化されてDBに保存）                   |

### Tavily API 設定（Web検索・HN Agent背景調査）

「Tavily API設定」から以下を設定：

| 項目           | 説明                                   |
| -------------- | -------------------------------------- |
| 設定名         | この設定を識別するための名前           |
| 有効           | この設定を有効にする（1つだけ有効可）  |
| APIキー        | Tavily APIキー（暗号化されてDBに保存） |
| タイムアウト   | APIリクエストのタイムアウト秒数        |

### Slack 通知設定

「Slack通知設定」から以下を設定：

| 項目          | 説明                                          |
| ------------- | --------------------------------------------- |
| 設定名        | この設定を識別するための名前                  |
| 有効          | この設定を有効にする（1つだけ有効可）         |
| Webhook URL   | Slack Incoming Webhook URL（暗号化されてDBに保存）|

### HN Agent 設定

「HN Agent設定」から以下を設定：

| 項目                  | 説明                                                |
| --------------------- | --------------------------------------------------- |
| Embedding次元数       | Embedding APIの出力次元数（small: 1536, large: 3072）|
| スコア閾値            | 調査をトリガーするスコアの閾値                      |
| 速度閾値              | 調査をトリガーするスコア上昇速度の閾値              |
| 類似度閾値            | 過去スレッド検索のcosine similarity閾値（0-1）      |
| ポーリング間隔        | HNフロントページのポーリング間隔（秒）              |

### HN Agent API

| メソッド | パス                              | 説明                                    |
| -------- | --------------------------------- | --------------------------------------- |
| `POST`   | `/hn-agent/run-all/`              | Watcher + Orchestrator一括実行          |
| `POST`   | `/hn-agent/watcher/run/`          | Watcherのみ手動実行                     |
| `POST`   | `/hn-agent/investigate/`          | 指定hn_idのスレッドをOrchestrator調査   |
| `GET`    | `/hn-agent/threads/`              | 監視中スレッド一覧                      |
| `GET`    | `/hn-agent/investigations/`       | 調査結果一覧                            |
| `GET`    | `/hn-agent/investigations/<id>/`  | 調査結果の詳細                          |

## テストの実行

```bash
# 全テスト実行（e2eテストを除く、カバレッジ付き）
uv run pytest tests/ -v --tb=short \
  --cov=user --cov=core --cov=integrations --cov=features \
  --cov-report=term-missing --cov-fail-under=80 -m "not e2e"

# 特定のアプリのテスト
uv run pytest tests/features/talk/
uv run pytest tests/user/
```

## API ドキュメント

Swagger UI でインタラクティブな API ドキュメントを確認できます：

- **Swagger UI**: `http://localhost:8000/swagger/`
- **ReDoc**: `http://localhost:8000/redoc/`
- **OpenAPI スキーマ**: `http://localhost:8000/schema/`

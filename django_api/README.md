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

# 暗号化キー（データベースに保存する機密情報の暗号化に使用）
ENCRYPTION_KEY=your-encryption-key

# OpenAI API（会話生成機能などのAI生成に使用）
OPENAI_API_KEY=your-openai-api-key

# Style-BERT-VITS2 API（音声合成機能）
TTS_SERVICE_URL=http://sbv2-api:5000
```

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

### LLM 設定（AI テキスト生成）

「LLM CONFIG」から以下を設定：

| 項目           | 説明                                 |
| -------------- | ------------------------------------ |
| モデル名       | OpenAI モデル名（例: `gpt-4o-mini`） |
| 最大トークン数 | 生成する最大トークン数               |
| 温度           | 生成のランダム性（0.0〜2.0）         |

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

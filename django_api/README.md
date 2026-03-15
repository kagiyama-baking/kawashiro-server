# Django API

REST API で複数の機能を提供するバックエンドサーバです。

## 機能一覧

| アプリ   | エンドポイント | 説明                                           |
| -------- | -------------- | ---------------------------------------------- |
| user     | `/user/`       | ユーザー認証・管理                             |
| onedrive | `/onedrive/`   | OneDrive ファイルアップロード・管理            |
| outlook  | `/outlook/`    | Outlook Calendar 予定取得                      |
| media    | `/media/`      | メディアファイル管理                           |
| tts      | `/tts/`        | テキスト読み上げ（Style-BERT-VITS2 プロキシ）  |
| weather  | `/weather/`    | 気象庁天気予報                                 |
| greeting | `/greeting/`   | 挨拶生成（設定ベースの AI 挨拶生成・TTS 対応） |

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
# 本番環境では十分にランダムな文字列を設定してください
ENCRYPTION_KEY=your-encryption-key

# OpenAI API（挨拶機能などのAI生成に使用）
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

### 挨拶設定（Greeting 機能）

「GREETING」→「挨拶設定」から複数の挨拶設定を登録できます：

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
curl -X POST http://localhost:8000/api/greeting/generate/ \
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

## Azure AD 設定

OneDrive/Outlook 機能を使用するには、Azure AD でアプリケーションを登録する必要があります。

### 必要な情報の取得

1. **テナントID**: Azure Portal > Azure Active Directory > 概要
2. **クライアントID**: Azure Portal > アプリの登録 > アプリケーション（クライアント）ID
3. **証明書サムプリント**: 証明書を登録後、証明書の詳細から確認

### 証明書の作成

```bash
# 秘密鍵の生成
openssl genrsa -out key.pem 2048

# 証明書署名要求の生成
openssl req -new -key key.pem -out cert.csr

# 自己署名証明書の生成
openssl x509 -req -days 365 -in cert.csr -signkey key.pem -out cert.cer

# サムプリントの取得
openssl x509 -in cert.cer -fingerprint -noout | sed 's/://g' | cut -d'=' -f2
```

### API 権限設定

Azure AD アプリケーションに以下のアプリケーション権限を付与し、管理者の同意を与えてください：

| 権限                | 用途                       |
| ------------------- | -------------------------- |
| Files.ReadWrite.All | OneDrive ファイル操作      |
| Calendars.Read      | Outlook カレンダー読み取り |
| User.Read.All       | ユーザー情報取得           |

## テストの実行

```bash
# 全テスト実行
uv run pytest

# カバレッジ付き
uv run pytest --cov=. --cov-report=html

# 特定のアプリのテスト
uv run pytest tests/greeting/
```

## API ドキュメント

Swagger UI でインタラクティブな API ドキュメントを確認できます：

- **Swagger UI**: `http://localhost:8000/api/docs/`
- **ReDoc**: `http://localhost:8000/api/redoc/`
- **OpenAPI スキーマ**: `http://localhost:8000/api/schema/`

## トラブルシューティング

### エラー: "有効なMicrosoft Graph API設定がありません"

Django 管理画面から MS Graph 設定を作成し、有効にしてください。

### エラー: "ENCRYPTION_KEY環境変数が設定されていません"

`.env` ファイルに `ENCRYPTION_KEY` を設定してください。

### エラー: "Failed to acquire token"

- Azure AD のテナント ID とクライアント ID が正しいか確認
- 証明書のサムプリントが正しいか確認
- 秘密鍵が正しい PEM 形式か確認
- API 権限が正しく設定されているか確認

### エラー: "朝のあいさつの設定が見つかりません"

Django 管理画面から朝のあいさつ設定を作成してください。

## 外部サービス・API

本プロジェクトは以下の外部サービス・API を使用しています。利用時は各サービスの規約を遵守してください。

| サービス                                                                | 用途                  | ライセンス・規約                                                                                |
| ----------------------------------------------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------- |
| [気象庁天気予報](https://www.jma.go.jp/bosai/forecast/)                 | 天気予報データ取得    | [政府標準利用規約（第2.0版）](https://www.jma.go.jp/jma/kishou/info/coment.html) - 出典記載必須 |
| [holidays-jp API](https://github.com/holidays-jp/api)                   | 日本の祝日判定        | MIT License                                                                                     |
| [OpenAI API](https://platform.openai.com/docs/)                         | AI テキスト生成       | 商用 API - 要 API キー                                                                          |
| [Microsoft Graph API](https://learn.microsoft.com/ja-jp/graph/overview) | OneDrive/Outlook 連携 | 商用 API - 要 Azure AD 設定                                                                     |

### 注意事項

- **気象庁データ**: 利用時は「出典：気象庁ホームページ」の記載が必要です

## 参考資料

- [Django REST Framework](https://www.django-rest-framework.org/)
- [Style-BERT-VITS2](https://github.com/litagin02/Style-Bert-VITS2) - 音声合成エンジン

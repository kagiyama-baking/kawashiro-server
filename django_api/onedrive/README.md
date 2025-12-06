# OneDrive API

Django REST FrameworkでMicrosoft Graph APIを使用してOneDriveにファイルをアップロードするAPIです。

## セットアップ

### 1. 環境変数を設定

`.env.sample`を参考に`.env`ファイルを作成し、以下の環境変数を設定してください：

```bash
# Django設定
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# 暗号化キー（データベースに保存する機密情報の暗号化に使用）
ENCRYPTION_KEY=your-encryption-key
```

### 2. 依存関係のインストール

```bash
uv sync
```

### 3. マイグレーションの実行

```bash
uv run ./manage.py migrate
```

### 4. Django管理画面でMicrosoft Graph API設定を行う

1. 管理ユーザーを作成：
   ```bash
   uv run ./manage.py createsuperuser
   ```

2. サーバーを起動：
   ```bash
   uv run ./manage.py runserver
   ```

3. Django管理画面（`http://localhost:8000/admin/`）にログイン

4. 「MS GRAPH CONFIG」を選択し、以下の情報を設定：
   - **テナントID**: Azure ADテナントID
   - **クライアントID**: Azure ADアプリケーションID
   - **証明書サムプリント**: 証明書のサムプリント
   - **秘密鍵**: PEM形式の秘密鍵
   - **対象ユーザー**: OneDriveにアクセスするユーザーのメールアドレス

## API エンドポイント

### 認証

すべてのエンドポイントはトークン認証が必要です。まず、トークンを取得してください：

```python
import requests

# トークンの取得
response = requests.post(
    "http://localhost:8000/api/user/token/",
    data={
        "username": "your_username",
        "password": "your_password"
    }
)
token = response.json()["token"]
```

### 1. ファイルアップロード

**エンドポイント:** `POST /api/onedrive/upload/`

**リクエスト:**
```python
import requests

headers = {
    "Authorization": f"Token {token}"
}

files = {
    "file": open("example.pdf", "rb")
}

data = {
    "folder_path": "/Documents",  # オプション（デフォルト: /）
    "file_name": "renamed.pdf"    # オプション（デフォルト: 元のファイル名）
}

response = requests.post(
    "http://localhost:8000/api/onedrive/upload/",
    headers=headers,
    files=files,
    data=data
)
```

**レスポンス:**
```json
{
    "message": "ファイルが正常にアップロードされました",
    "file_info": {
        "id": "01234567890ABC",
        "name": "renamed.pdf",
        "size": 1024,
        "created_at": "2024-01-01T00:00:00Z",
        "modified_at": "2024-01-01T00:00:00Z",
        "web_url": "https://...",
        "download_url": "https://...",
        "is_folder": false
    }
}
```

### 2. フォルダ作成

**エンドポイント:** `POST /api/onedrive/folder/`

**リクエスト:**
```python
headers = {
    "Authorization": f"Token {token}",
    "Content-Type": "application/json"
}

data = {
    "folder_name": "NewFolder",
    "parent_path": "/Documents"  # オプション（デフォルト: /）
}

response = requests.post(
    "http://localhost:8000/api/onedrive/folder/",
    headers=headers,
    json=data
)
```

**レスポンス:**
```json
{
    "message": "フォルダが正常に作成されました",
    "folder_info": {
        "id": "01234567890ABC",
        "name": "NewFolder",
        "created_at": "2024-01-01T00:00:00Z",
        "modified_at": "2024-01-01T00:00:00Z",
        "web_url": "https://...",
        "is_folder": true
    }
}
```

### 3. ファイル一覧取得

**エンドポイント:** `GET /api/onedrive/list/`

**リクエスト:**
```python
headers = {
    "Authorization": f"Token {token}"
}

params = {
    "folder_path": "/Documents"  # オプション（デフォルト: /）
}

response = requests.get(
    "http://localhost:8000/api/onedrive/list/",
    headers=headers,
    params=params
)
```

**レスポンス:**
```json
{
    "folder_path": "/Documents",
    "count": 2,
    "files": [
        {
            "id": "01234567890ABC",
            "name": "file1.pdf",
            "size": 1024,
            "created_at": "2024-01-01T00:00:00Z",
            "modified_at": "2024-01-01T00:00:00Z",
            "web_url": "https://...",
            "download_url": "https://...",
            "is_folder": false
        },
        {
            "id": "01234567890DEF",
            "name": "SubFolder",
            "created_at": "2024-01-01T00:00:00Z",
            "modified_at": "2024-01-01T00:00:00Z",
            "web_url": "https://...",
            "is_folder": true
        }
    ]
}
```

## エラーレスポンス

**認証エラー（401）:**
```json
{
    "detail": "Authentication credentials were not provided."
}
```

**バリデーションエラー（400）:**
```json
{
    "file": ["This field is required."]
}
```

**設定エラー（500）:**
```json
{
    "error": "Microsoft Graph API設定がデータベースに存在しません。Django管理画面から設定を行ってください。"
}
```

**サーバーエラー（500）:**
```json
{
    "error": "Failed to upload file: [詳細なエラーメッセージ]"
}
```

## 注意事項

- ファイルサイズの制限はMicrosoft Graph APIの制限に従います（通常4MB、大きなファイルは別途アップロードセッションが必要）
- 証明書認証を使用しているため、秘密鍵と証明書のサムプリントが必要です
- 設定はDjango管理画面から行います（秘密鍵は暗号化されてデータベースに保存されます）
- 対象ユーザーで指定したユーザーのOneDriveにアクセスします

# OneDrive API

Django REST FrameworkでMicrosoft Graph APIを使用してOneDriveにファイルをアップロードするAPIです。

## セットアップ

### 1. 必要な環境変数を設定

`.env.sample`を参考に`.env`ファイルを作成し、以下の環境変数を設定してください：

```bash
# Microsoft Graph API設定
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CERT_THUMBPRINT=your-cert-thumbprint
AZURE_CERT_KEY_FILE=/path/to/key.pem
TARGET_USER=user@example.com
```

### 2. 依存関係のインストール

```bash
uv sync
```

### 3. マイグレーションの実行

```bash
uv run ./manage.py migrate
```

### 4. サーバーの起動

```bash
uv run ./manage.py runserver
```

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

**サーバーエラー（500）:**
```json
{
    "error": "Failed to upload file: [詳細なエラーメッセージ]"
}
```

## 注意事項

- ファイルサイズの制限はMicrosoft Graph APIの制限に従います（通常4MB、大きなファイルは別途アップロードセッションが必要）
- 証明書認証を使用しているため、秘密鍵ファイルと証明書のサムプリントが必要です
- TARGET_USERで指定したユーザーのOneDriveにアクセスします
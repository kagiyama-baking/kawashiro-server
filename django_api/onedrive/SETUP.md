# OneDrive API セットアップガイド

## 環境変数の設定

### 1. .envファイルの作成

プロジェクトのルートディレクトリ（`/home/hakotsuki/Repository/kawashiro-server/django_api/`）に`.env`ファイルを作成してください。

```bash
cd /home/hakotsuki/Repository/kawashiro-server/django_api/
cp .env.sample .env
```

### 2. Azure ADアプリケーションの設定

Azure PortalでAzure ADアプリケーションを作成し、以下の情報を取得してください：

1. **AZURE_TENANT_ID**: Azure ADテナントID
   - Azure Portal > Azure Active Directory > 概要 > テナントID

2. **AZURE_CLIENT_ID**: アプリケーションID
   - Azure Portal > Azure Active Directory > アプリの登録 > アプリケーション（クライアント）ID

3. **AZURE_CERT_THUMBPRINT**: 証明書のサムプリント
   - 証明書を登録後、証明書の詳細から確認

4. **AZURE_CERT_KEY_FILE**: 秘密鍵ファイルのパス
   - Docker secrets経由でマウントされるパス
   - Dockerコンテナ内: `/run/secrets/django_api_graph_key`

5. **TARGET_USER**: アクセス対象のユーザー
   - OneDriveにアクセスするユーザーのメールアドレス
   - 例: `user@example.com`

### 3. .envファイルの編集

`.env`ファイルを以下のように編集してください：

```env
# Django設定
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# Microsoft Graph API設定
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CERT_THUMBPRINT=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# Docker secretsを使用（コンテナ内のパス）
AZURE_CERT_KEY_FILE=/run/secrets/django_api_graph_key
TARGET_USER=your-email@example.com
```

### 4. 証明書の配置

秘密鍵ファイルを`secrets`ディレクトリに配置してください：

```bash
# secretsディレクトリに秘密鍵を配置
cp /path/to/your/key.pem /home/hakotsuki/Repository/kawashiro-server/secrets/django_api_graph_key.pem
```

もし証明書ファイルがない場合は、以下の手順で作成してください：

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

### 5. Azure ADでの権限設定

Azure ADアプリケーションに以下のAPI権限を付与してください：

1. Microsoft Graph API
   - Files.ReadWrite.All（アプリケーション）
   - User.Read.All（アプリケーション）

権限を追加後、管理者の同意を与えてください。

### 6. 環境変数の確認

設定が正しいか確認するには、Djangoシェルを使用します：

```bash
cd /home/hakotsuki/Repository/kawashiro-server/django_api/
uv run ./manage.py shell
```

```python
from django.conf import settings
print("AZURE_TENANT_ID:", settings.AZURE_TENANT_ID)
print("AZURE_CLIENT_ID:", settings.AZURE_CLIENT_ID)
print("AZURE_CERT_THUMBPRINT:", settings.AZURE_CERT_THUMBPRINT)
print("AZURE_CERT_KEY_FILE:", settings.AZURE_CERT_KEY_FILE)
print("TARGET_USER:", settings.TARGET_USER)

# ファイルの存在確認
import os
if settings.AZURE_CERT_KEY_FILE:
    print("秘密鍵ファイル存在:", os.path.exists(settings.AZURE_CERT_KEY_FILE))
```

## トラブルシューティング

### エラー: "以下の環境変数が設定されていません"

`.env`ファイルが正しく配置されているか、環境変数が設定されているか確認してください。

### エラー: "秘密鍵ファイルが見つかりません"

`AZURE_CERT_KEY_FILE`のパスが正しいか確認してください。絶対パスで指定する必要があります。

### エラー: "Failed to acquire token"

- Azure ADのテナントIDとクライアントIDが正しいか確認
- 証明書のサムプリントが正しいか確認
- API権限が正しく設定されているか確認
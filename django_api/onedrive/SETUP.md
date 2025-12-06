# OneDrive API セットアップガイド

## 環境変数の設定

### 1. .envファイルの作成

プロジェクトのルートディレクトリ（`/home/hakotsuki/Repository/kawashiro-server/django_api/`）に`.env`ファイルを作成してください。

```bash
cd /home/hakotsuki/Repository/kawashiro-server/django_api/
cp .env.sample .env
```

### 2. .envファイルの編集

`.env`ファイルを以下のように編集してください：

```env
# Django設定
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# 暗号化キー（データベースに保存する機密情報の暗号化に使用）
# 本番環境では十分にランダムな文字列を設定してください
ENCRYPTION_KEY=your-encryption-key-here
```

### 3. マイグレーションの実行

```bash
uv run ./manage.py migrate
```

### 4. Django管理画面でMicrosoft Graph API設定を行う

Azure PortalでAzure ADアプリケーションを作成し、以下の情報を取得してください：

1. **テナントID**: Azure ADテナントID
   - Azure Portal > Azure Active Directory > 概要 > テナントID

2. **クライアントID**: アプリケーションID
   - Azure Portal > Azure Active Directory > アプリの登録 > アプリケーション（クライアント）ID

3. **証明書サムプリント**: 証明書のサムプリント
   - 証明書を登録後、証明書の詳細から確認

4. **秘密鍵**: PEM形式の秘密鍵
   - 証明書の秘密鍵ファイルの内容

5. **対象ユーザー**: アクセス対象のユーザー
   - OneDriveにアクセスするユーザーのメールアドレス
   - 例: `user@example.com`

これらの情報をDjango管理画面から設定します：

1. 管理ユーザーを作成：
   ```bash
   uv run ./manage.py createsuperuser
   ```

2. サーバーを起動：
   ```bash
   uv run ./manage.py runserver
   ```

3. Django管理画面（`http://localhost:8000/admin/`）にログイン

4. 「MS GRAPH CONFIG」を選択し、上記の情報を入力

   **注意**: 秘密鍵は暗号化されてデータベースに保存されます。

### 5. 証明書の作成（必要な場合）

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

### 6. Azure ADでの権限設定

Azure ADアプリケーションに以下のAPI権限を付与してください：

1. Microsoft Graph API
   - Files.ReadWrite.All（アプリケーション）
   - User.Read.All（アプリケーション）

権限を追加後、管理者の同意を与えてください。

### 7. 設定の確認

設定が正しいか確認するには、Djangoシェルを使用します：

```bash
cd /home/hakotsuki/Repository/kawashiro-server/django_api/
uv run ./manage.py shell
```

```python
from onedrive.config import get_ms_graph_settings

try:
    settings = get_ms_graph_settings()
    print("テナントID:", settings.tenant_id)
    print("クライアントID:", settings.client_id)
    print("サムプリント:", settings.cert_thumbprint)
    print("対象ユーザー:", settings.target_user)
    print("秘密鍵が設定されています:", bool(settings.private_key))
except Exception as e:
    print("エラー:", e)
```

## トラブルシューティング

### エラー: "Microsoft Graph API設定がデータベースに存在しません"

Django管理画面から設定を行ってください。

### エラー: "以下の設定が未入力です: ..."

Django管理画面で、表示されている設定項目を入力してください。

### エラー: "Failed to acquire token"

- Azure ADのテナントIDとクライアントIDが正しいか確認
- 証明書のサムプリントが正しいか確認
- 秘密鍵が正しいPEM形式か確認
- API権限が正しく設定されているか確認

### エラー: "ENCRYPTION_KEY環境変数が設定されていません"

`.env`ファイルに`ENCRYPTION_KEY`を設定してください。この値は、データベースに保存される秘密鍵の暗号化に使用されます。

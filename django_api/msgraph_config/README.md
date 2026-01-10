# Microsoft Graph API 共通設定

OneDrive API および Outlook Calendar API で使用する Microsoft Graph API の共通設定モジュールです。

## セットアップ

### 1. 環境変数を設定

`.env.sample`を参考に`.env`ファイルを作成してください：

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
```

### 2. マイグレーションの実行

```bash
uv run ./manage.py migrate
```

### 3. Django管理画面でMicrosoft Graph API設定を行う

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
   - **秘密鍵**: PEM形式の秘密鍵（暗号化されてDBに保存）
   - **対象ユーザー**: アクセス対象のユーザーメールアドレス

## Azure AD設定

### 必要な情報の取得

1. **テナントID**
   - Azure Portal > Azure Active Directory > 概要 > テナントID

2. **クライアントID**
   - Azure Portal > Azure Active Directory > アプリの登録 > アプリケーション（クライアント）ID

3. **証明書サムプリント**
   - 証明書を登録後、証明書の詳細から確認

4. **秘密鍵**
   - 証明書の秘密鍵ファイルの内容（PEM形式）

### 証明書の作成（必要な場合）

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

### API権限設定

Azure ADアプリケーションに以下のAPI権限を付与し、管理者の同意を与えてください：

| 権限 | 種類 | 用途 |
|------|------|------|
| Files.ReadWrite.All | アプリケーション | OneDriveファイル操作 |
| Calendars.Read | アプリケーション | Outlookカレンダー読み取り |
| User.Read.All | アプリケーション | ユーザー情報取得 |

## 設定の確認

```bash
uv run ./manage.py shell
```

```python
from ms_graph.config import get_ms_graph_settings

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

### エラー: "有効なMicrosoft Graph API設定がありません"

Django管理画面から設定を作成し、有効にしてください。

### エラー: "以下の項目が未入力です: ..."

Django管理画面で、表示されている設定項目を入力してください。

### エラー: "Failed to acquire token"

- Azure ADのテナントIDとクライアントIDが正しいか確認
- 証明書のサムプリントが正しいか確認
- 秘密鍵が正しいPEM形式か確認
- API権限が正しく設定されているか確認

### エラー: "ENCRYPTION_KEY環境変数が設定されていません"

`.env`ファイルに`ENCRYPTION_KEY`を設定してください。

# Kawashiro Server

🌊 Docker Compose を使用した Web サービス群

## 概要

Kawashiro Server は、Docker コンテナベースの Web サービス群です。複数の Web サービスを統一されたドメインで提供し、サブドメインによるルーティングを行います。

## サービス

-   🔀 **リバースプロキシ**: Nginx ベースの高性能リバースプロキシ
-   🧪 **テスト環境**: 開発・検証用のテスト Web サーバー内蔵

## プロジェクト構成

```
kawashiro-server/
├── docker-compose.yaml         # メインのDocker Compose設定
├── README.md                   # このファイル
│
├── reverse_proxy/              # リバースプロキシ設定
│   ├── Dockerfile              # Nginxコンテナ定義
│   ├── nginx.conf              # メインのNginx設定
│   ├── conf.d/                 # サイト別設定
│   │   └── default.conf        # デフォルトサイト設定
│   └── html/                   # 静的ファイル
│       └── 404.html            # カスタム404ページ
│
└── test_web/                   # テスト用Webサーバー
    ├── Dockerfile              # テストサーバーコンテナ
    └── index.html              # テストページ
```

## アーキテクチャ

```
Internet
    │
    ▼
┌─────────────┐
│ Nginx Proxy │ :80
│ (Port 80)   │
└─────────────┘
    │
    ├── test.[domain] ──► Test Web Server :8080
    └── [domain] ─────► 404 Page
```

## 必要な環境

-   Docker Engine 20.10.0+
-   Docker Compose 2.0.0+

## インストール・セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/kagiyama-baking/kawashiro-server.git
cd kawashiro-server
```

### 2. サーバーの起動

```bash
# すべてのサービスを起動
docker compose up -d

# ログを確認
docker compose logs -f
```

### 3. 動作確認

```bash
# ヘルスチェック
curl http://localhost/health

# テストサーバー（サブドメイン経由）
curl -H "Host: test.localhost" http://localhost/
```

## 使用方法

### サービスの管理

```bash
# サービスの起動
docker compose up -d

# サービスの停止
docker compose down

# サービスの再起動
docker compose restart

# 特定のサービスのみ再起動
docker compose restart reverse-proxy
```

### ログの確認

```bash
# 全サービスのログ
docker compose logs -f

# 特定のサービスのログ
docker compose logs -f reverse-proxy
docker compose logs -f test-web
```

### 設定の更新

```bash
# 設定ファイル変更後、リバースプロキシの再読み込み
docker compose exec reverse-proxy nginx -s reload

# または再起動
docker compose restart reverse-proxy
```

## アクセス方法

### 基本アクセス

-   **ヘルスチェック**: `http://localhost/health`
-   **メインドメイン**: `http://localhost/` → カスタム 404 ページ
-   **テストサーバー**: `http://test.localhost/` → テスト用 Web サーバー

### 本番環境での使用

実際のドメインでの使用時:

-   **メインサイト**: `https://yourdomain.com/` → 404 ページ
-   **テストサイト**: `https://test.yourdomain.com/` → テスト用サーバー

## カスタマイズ

### 新しいサービスの追加

1. `docker-compose.yaml`にサービスを追加:

```yaml
services:
    your-app:
        image: your-app:latest
        container_name: your-app
        networks:
            - proxy-network
```

2. `reverse_proxy/conf.d/default.conf`にルーティングを追加:

```nginx
# あなたのアプリ用設定
server {
    listen 80;
    server_name ~^app\.(.*)$;

    location / {
        proxy_pass http://your-app:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### SSL/HTTPS 対応

1. SSL 証明書を`reverse_proxy/ssl/`ディレクトリに配置
2. `docker-compose.yaml`の HTTPS 設定のコメントアウトを解除
3. `reverse_proxy/conf.d/`に SSL 設定を追加

## 開発

### 開発環境での起動

```bash
# 開発モードで起動（ファイル変更が即座に反映）
docker compose up --build

# 特定のサービスのみビルド
docker compose build reverse-proxy
```

### デバッグ

```bash
# コンテナ内でコマンド実行
docker compose exec reverse-proxy /bin/sh

# 設定ファイルの検証
docker compose exec reverse-proxy nginx -t
```

## トラブルシューティング

### よくある問題

#### ポート 80 が既に使用されている

```bash
# 使用中のプロセスを確認
sudo lsof -i :80

# または別のポートを使用
# docker-compose.yamlでポート設定を変更
ports:
  - '8080:80'  # localhost:8080でアクセス
```

#### 設定変更が反映されない

```bash
# Nginxの設定をテスト
docker compose exec reverse-proxy nginx -t

# コンテナを完全に再ビルド
docker compose down
docker compose up --build -d
```

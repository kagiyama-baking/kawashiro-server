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

### Reverse Proxy

各コンテナへ、Web アクセスは、Reverse Proxy に集約する。  
Reverse Proxy は、ホスト側のポート TCP/80 でアクセスを受け付け、
サブドメインに応じて対応するコンテナ側ポートへ転送する。

```
   Browser
      │
      ▼
┌───────────────┐
│ Reverse Proxy │ :80（ホスト）
│ (Nginx)       │
└───────────────┘
      │                        ┌───────────────┐
      ├── test.example.com ──► │ Test Web      │ :8080 (コンテナ)
      │                        │ (Nginx)       │
      │                        └───────────────┘
      │                        ┌───────────────┐
      └── example.com ───────► │ Reverse Proxy │ :8080 (コンテナ)
                               │ (Nginx)       │
                               └───────────────┘
```

### 永続化ボリューム

永続化したいボリュームは、`docker-compose.yaml`で指定する。
`volomes`の配下は、コンテナ名ごとに整理する。

```yaml
volumes:
    # ログの永続化例（nginx）
    - ./volumes/[container_name]/log/nginx:/var/log/nginx
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

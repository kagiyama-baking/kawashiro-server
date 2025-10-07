# 鍵山製パン社内 Web システム

[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Nginx](https://img.shields.io/badge/Nginx-009639?style=for-the-badge&logo=nginx&logoColor=white)](https://nginx.org/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)](https://github.com/features/actions)

## 概要

Docker コンテナベースの Web サービス群です。複数の Web サービスを統一されたドメインで提供し、サブドメインによるルーティングを行います。

## サービス

-   🔀 **リバースプロキシ**: Nginx ベースの高性能リバースプロキシ
-   🧪 **テスト環境**: 開発・検証用のテスト Web サーバー内蔵
-   📷 **[Immich](https://github.com/immich-app/immich)**: セルフホスト型の OSS 写真管理・共有プラットフォーム（Google Photos の代替）

## 特徴

-   🚀 **CI/CD**: GitHub Actions による自動ビルド・テスト・デプロイ
-   📦 **コンテナレジストリ**: GitHub Container Registry へのイメージ公開
-   🔐 **ビルド証明**: SLSA Build Provenance による信頼性の担保
-   📋 **SBOM**: ソフトウェア部品表（CycloneDX）の自動生成

## プロジェクト構成

```
kawashiro-server/
├── docker-compose.yml          # メインのDocker Compose設定
├── README.md                   # このファイル
│
├── .github/                    # GitHub設定
│   ├── workflows/              # GitHub Actionsワークフロー
│   │   ├── build.yml           # ビルド・プッシュ（develop）
│   │   └── pr-checks.yml       # PRチェック
│   └── copilot-instructions.md # Copilotレビュー設定
│
├── reverse_proxy/              # リバースプロキシ設定
│   ├── Dockerfile              # Nginxコンテナ定義
│   ├── nginx.conf              # メインのNginx設定
│   ├── conf.d/                 # サイト別設定
│   │   └── default.conf        # デフォルトサイト設定
│   └── html/                   # 静的ファイル
│       ├── index.html          # トップページ
│       └── 404.html            # カスタム404ページ
│
├── test_web/                   # テスト用Webサーバー
│   ├── Dockerfile              # テストサーバーコンテナ
│   ├── conf.d/                 # Nginx設定
│   │   └── default.conf        # デフォルト設定
│   └── html/                   # 静的ファイル
│       └── index.html          # テストページ
│
└── volumes/                    # 永続化データ
    ├── reverse-proxy/
    │   └── log/nginx/          # リバースプロキシのログ
    ├── test-web/
    │   └── log/nginx/          # テストWebのログ
    └── immich/
        ├── data/               # アップロード写真データ
        └── log/                # アプリケーションログ
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
      │                         ┌───────────────┐
      ├── test.example.com ──►  │ Test Web      │ :8080 (コンテナ)
      │                         │ (Nginx)       │
      │                         └───────────────┘
      │                         ┌───────────────┐
      ├── album.example.com ─►  │ Immich        │ :2283 (コンテナ)
      │                         │ (Server)      │
      │                         └───────────────┘
      │                         ┌───────────────┐
      └── example.com ────────► │ Reverse Proxy │ :8080 (コンテナ)
                                │ (Nginx)       │
                                └───────────────┘
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

# Immich（サブドメイン経由）
curl -H "Host: album.localhost" http://localhost/
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
docker compose logs -f immich
docker compose logs -f immich-machine-learning
docker compose logs -f immich-redis
docker compose logs -f immich-postgres
```

### 設定の更新

```bash
# 設定ファイル変更後、リバースプロキシの再読み込み
docker compose exec reverse-proxy nginx -s reload

# または再起動
docker compose restart reverse-proxy
```

## CI/CD

### GitHub Actions ワークフロー

#### ビルド・プッシュ（develop ブランチ）

develop ブランチへのプッシュ時に自動実行：

1. マルチアーキテクチャビルド（amd64, arm64）
2. GitHub Container Registry へプッシュ
3. SBOM（ソフトウェア部品表）生成
4. ビルド証明（Build Provenance）の添付

```bash
# イメージの取得
docker pull ghcr.io/kagiyama-baking/kawashiro-server/reverse-proxy:staging
docker pull ghcr.io/kagiyama-baking/kawashiro-server/test-web:staging
```

#### PR チェック

Pull Request 作成時に自動実行：

1. Docker イメージのビルド
2. Nginx 設定の構文チェック
3. コンテナの起動確認
4. リバースプロキシ機能テスト

### コンテナイメージのタグ戦略

-   `staging`: develop ブランチの最新ビルド
-   `release`: 本番環境用の安定版
-   `sha-<commit>`: 特定コミットのビルド

## 本番環境へのデプロイ

本番環境では`docker-compose-prod.yml`を使用します。このファイルは、GitHub Container Registryにプッシュされたリリースイメージを使用します。

### 初回セットアップ

1. **必要なファイルの準備**
   ```bash
   # リポジトリのクローン
   git clone https://github.com/kagiyama-baking/kawashiro-server.git
   cd kawashiro-server

   # .envファイルの作成（Immich用の環境変数）
   cp .env.example .env
   # 必要に応じて.envファイルを編集
   ```

2. **イメージの取得と起動**
   ```bash
   # 最新のイメージをプル
   docker compose -f docker-compose-prod.yml pull

   # サービスの起動
   docker compose -f docker-compose-prod.yml up -d
   ```

### 運用コマンド

```bash
# イメージの更新と再起動
docker compose -f docker-compose-prod.yml pull
docker compose -f docker-compose-prod.yml up -d --force-recreate

# ログの確認
docker compose -f docker-compose-prod.yml logs -f

# 特定サービスのログ確認
docker compose -f docker-compose-prod.yml logs -f reverse-proxy

# サービスの停止
docker compose -f docker-compose-prod.yml down

# サービスの状態確認
docker compose -f docker-compose-prod.yml ps
```

### 本番環境で使用されるイメージ

- `ghcr.io/kagiyama-baking/kawashiro-server/reverse-proxy:release`
- `ghcr.io/kagiyama-baking/kawashiro-server/test-web:release`

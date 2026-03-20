# 鍵山製パン社内 Web アプリケーション

[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)](https://github.com/features/actions)

## 概要

Docker コンテナベースの Web アプリケーションです。
本番環境のデプロイとリバースプロキシ（Traefik）は [internal.kagiyama.net](https://github.com/kagiyama-baking/internal.kagiyama.net) リポジトリ（Ansible）が管理します。このリポジトリには docker-compose.yml が含まれますが、開発環境用の設定であり、本番環境では使用しません。

## サービス

- 🐍 **Django API**: REST API で複数の機能を提供するバックエンドサーバ
    - 🛠️ **Core**: 共通機能・ユーティリティ（カスタムUserモデル、暗号化）
    - 🔐 **User**: ユーザー認証・管理機能
    - **integrations/** - 外部サービス連携
        - 🤖 **LLM**: OpenAI API 設定・クライアント（テキスト生成）
        - 🔗 **MS Graph**: Microsoft Graph API 設定・認証・クライアント
        - ☁️ **OneDrive**: Microsoft OneDrive との統合機能（ファイルアップロード・管理）
        - 📅 **Outlook**: Outlook Calendar 予定取得機能
        - 🔊 **TTS**: テキスト読み上げ機能（Style-BERT-VITS2 プロキシ）
        - 🌤️ **Weather**: 気象庁天気予報 API（今日・明日・明後日の天気、気温、降水確率）
    - **features/** - ビジネス機能
        - 🎙️ **Greeting**: 挨拶 API（設定ベースの柔軟な挨拶生成、天気・予定・日時情報を選択可能、TTS 音声合成対応）
        - 📁 **Media**: メディアファイル管理機能
- 🎤 **Style-BERT-VITS2 API**: 高品質な日本語音声合成サービス（GPU対応）

## 特徴

- 🚀 **CI/CD**: GitHub Actions による自動ビルド・テスト・リリース
- 📦 **コンテナレジストリ**: GitHub Container Registry へのイメージ公開
- 🔐 **ビルド証明**: SLSA Build Provenance による信頼性の担保
- 📋 **SBOM**: ソフトウェア部品表（CycloneDX）の自動生成
- 🛡️ **脆弱性スキャン**: Trivy によるイメージ検査
- 🔒 **暗号化**: 機密情報の暗号化保存（OneDrive 設定など）
- 🐍 **最新 Python 環境**: uv を使用した高速なパッケージ管理
- ✅ **テストカバレッジ**: pytest によるテスト自動化とカバレッジ計測

## プロジェクト構成

```
kawashiro-server/
├── docker-compose.yml          # 開発用のDocker Compose設定
├── README.md                   # このファイル
│
├── .github/                    # GitHub設定
│   ├── workflows/              # GitHub Actionsワークフロー
│   │   ├── build.yml           # ビルド・プッシュ（develop）
│   │   ├── release.yml         # リリースタグ付け（main）
│   │   ├── pr-checks.yml       # PRチェック
│   │   └── cleanup-images.yml  # 古いイメージのクリーンアップ
│   └── copilot-instructions.md # Copilotレビュー設定
│
├── django_api/                 # Django REST API
│   ├── Dockerfile              # Django APIコンテナ
│   ├── pyproject.toml          # Python依存関係（uv使用）
│   ├── manage.py               # Djangoコマンド
│   ├── django_api/             # メインプロジェクト設定
│   │   ├── settings.py         # Django設定
│   │   ├── urls.py             # URLルーティング
│   │   ├── asgi.py             # ASGIエントリーポイント
│   │   └── wsgi.py             # WSGIエントリーポイント
│   ├── core/                   # コアアプリ（カスタムUserモデル、暗号化）
│   ├── user/                   # ユーザー認証アプリ
│   ├── health/                 # ヘルスチェックアプリ
│   ├── integrations/           # 外部サービス連携
│   │   ├── llm/                # LLM設定・クライアント（OpenAI API）
│   │   ├── msgraph/            # Microsoft Graph API設定・クライアント
│   │   ├── onedrive/           # OneDrive連携API
│   │   ├── outlook/            # Outlook Calendar連携API
│   │   ├── tts/                # TTS読み上げ（sbv2-apiプロキシ）
│   │   └── weather/            # 気象庁天気予報
│   ├── features/               # ビジネス機能
│   │   ├── greeting/           # 挨拶生成（LLM + 天気 + 予定 + TTS統合）
│   │   └── media/              # 画像処理（ZIP→PDF変換、画像形式変換）
│   └── tests/                  # テストコード
│       ├── integrations/       # 外部サービス連携テスト
│       ├── features/           # ビジネス機能テスト
│       ├── user/               # ユーザーテスト
│       └── health/             # ヘルスチェックテスト
│
└── sbv2_api/                   # Style-BERT-VITS2 APIサーバー（GPU）
    ├── Dockerfile              # コンテナ定義（CUDA 11.8）
    ├── server.py               # FastAPIサーバー
    └── config.yml              # モデル設定
```

## 必要な環境

- Docker Engine 20.10.0+
- Docker Compose 2.0.0+
- NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)（sbv2-api 用）

## インストール・セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/kagiyama-baking/kawashiro-server.git
cd kawashiro-server
```

### 2. 環境変数の設定

```bash
# Django API用の環境変数ファイルを作成
cp django_api/.env.sample django_api/.env

# .envファイルを編集して必要な値を設定
nano django_api/.env
```

### 3. 永続化ディレクトリの準備

```bash
# Django APIの永続化データ用ディレクトリを作成
sudo mkdir -p /opt/app/django-api/staticfiles
sudo touch /opt/app/django-api/db.sqlite3
sudo chown -R $USER:$USER /opt/app/
```

### 4. サーバーの起動

```bash
# すべてのサービスを起動
docker compose up -d

# ログを確認
docker compose logs -f
```

### 5. 動作確認

```bash
# Django API ヘルスチェック
curl http://localhost:8000/schema/
```

## 環境変数設定

### Django API 設定

`django_api/.env` ファイルに以下の環境変数を設定してください（`.env.sample` を参照）：

```bash
# Django設定（必須）
SECRET_KEY=YOUR_SECRET_KEY

# デバッグモード（デフォルト: False）
DEBUG=False

# 許可ホスト（カンマ区切り、デフォルト: localhost）
ALLOWED_HOSTS=localhost,127.0.0.1

# データベースに保存する機密情報の暗号化に使用
ENCRYPTION_KEY=YOUR_ENCRYPTION_KEY

# Style-BERT-VITS2 API（デフォルト: http://sbv2-api:5000）
TTS_SERVICE_URL=http://sbv2-api:5000

# リバースプロキシ経由時のCSRF信頼済みオリジン（本番環境用）
CSRF_TRUSTED_ORIGINS=https://api.example.com
```

その他の設定（Microsoft Graph API、OpenAI API キーなど）は Django 管理画面（`/admin/`）から設定します。

## 使用方法

### サービスの管理

```bash
# サービスの起動
docker compose up -d

# サービスの停止
docker compose down

# サービスの再起動
docker compose restart
```

### ログの確認

```bash
# 全サービスのログ
docker compose logs -f

# 特定のサービスのログ
docker compose logs -f django-api
```

## CI/CD

### デプロイメントパイプライン

本プロジェクトでは、GitHub Actions を活用した 3 段階のデプロイメントパイプラインを構築しています。
本番デプロイは [internal.kagiyama.net](https://github.com/kagiyama-baking/internal.kagiyama.net)（Ansible）が担当します。

### GitHub Actions ワークフロー

```mermaid
flowchart LR

  %% 開発フェーズ（PR → develop）
  subgraph Dev["開発フェーズ"]
    direction TB
    A[feature/* ブランチ<br/>push & PR]
    B[PR to develop]
    C[pr-checks.yml<br/>━━━━━━━━━━<br/>・Dockerfile セキュリティスキャン<br/>・Ruff lint/format<br/>・pytest（カバレッジ80%以上）<br/>・Docker compose build<br/>・Django migrate<br/>・Django API 機能テスト]
    D[develop へマージ]

    A --> B
    B --> C
    C --> D
  end

  %% ステージング（develop push）
  subgraph Stg["ステージング"]
    direction TB
    E[develop push]
    F[build.yml<br/>━━━━━━━━━━<br/>・Multi-arch build<br/>・GHCR へ push<br/>・タグ: staging<br/>・SBOM生成]

    E --> F
  end

  %% リリース（main push）
  subgraph Rel["リリース"]
    direction TB
    G[develop → main]
    H[release.yml<br/>━━━━━━━━━━<br/>・イメージ確認<br/>・staging → release リタグ]

    G --> H
  end

  %% フェーズ間の接続
  Dev -.->|develop branch| Stg
  Stg -.->|staging images| Rel
```

### ワークフロー詳細

#### 1. PR チェック (`pr-checks.yml`)

**トリガー条件:**

- `develop`ブランチへの Pull Request 作成・更新時
- 手動実行（`workflow_dispatch`）

**実行内容:**

```yaml
# 主要なチェック項目
- Dockerfileセキュリティスキャン（Trivy config scan）
- Ruff リンター・フォーマッターチェック
- pytest（カバレッジ80%以上必須）
- Docker Composeビルド検証
- Django APIのマイグレーション・collectstaticテスト
- Django API 機能テスト（OpenAPIスキーマ・Swagger UI）
```

**タイムアウト:** 15 分

#### 2. ビルド・プッシュ (`build.yml`)

**トリガー条件:**

- `develop`ブランチへのプッシュ時
- 手動実行（`workflow_dispatch`）

**実行内容:**

```yaml
# ビルド対象サービス
services:
  - django-api

# 各サービスに対して実行
- マルチアーキテクチャビルド (linux/amd64, linux/arm64)
- GitHub Container Registry (GHCR) へプッシュ
- SBOM (Software Bill of Materials) 生成
- Build Provenance (SLSA Level 3) 添付
```

**生成されるタグ:**

- `staging` - 最新のステージングビルド
- `sha-<7文字のSHA>` - コミット固有のタグ

**タイムアウト:** 30 分

#### 3. リリース (`release.yml`)

**トリガー条件:**

- `main`ブランチへのプッシュ時
- 手動実行

**実行内容:**

```yaml
# リリースフロー
1. verify-images: stagingイメージの存在確認
2. tag-release: staging → release/latest リタグ
3. summary: リリースサマリー出力
```

**本番タグ:**

- `release` - 本番環境用の最新リリース
- `latest` - 最新版（互換性のため）

### コンテナイメージのタグ戦略

| タグ           | 用途             | 更新タイミング                 |
| -------------- | ---------------- | ------------------------------ |
| `staging`      | ステージング環境 | develop ブランチへのプッシュ時 |
| `release`      | 本番環境         | main ブランチへのマージ時      |
| `latest`       | 最新版（互換性） | main ブランチへのマージ時      |
| `sha-<commit>` | 特定バージョン   | 各ビルド時                     |

### ロールバック手順

問題が発生した場合のロールバック：

```bash
# 特定のSHAタグを使用してロールバック
docker pull ghcr.io/kagiyama-baking/kawashiro-server/django-api:sha-abc1234

# Ansible側でタグを指定してデプロイ
```

### ブランチ保護ルール

#### develop ブランチ

- PR が必須
- ステータスチェック必須（pr-checks）
- レビュー承認が必要
- 直接プッシュ禁止

#### main ブランチ

- PR が必須
- develop からのマージのみ許可
- 管理者承認が必要
- タグ付けは自動化

### CI/CD 環境変数

GitHub Secrets に設定が必要な環境変数：

```yaml
# 必須（自動設定）
GITHUB_TOKEN: ${{ github.token }}
```

## トラブルシューティング

### よくある問題と解決方法

#### 1. コンテナが起動しない

```bash
# コンテナの状態を確認
docker compose ps

# 詳細なログを確認
docker compose logs -f [サービス名]

# 原因と対処法
# - ポート競合: 他のサービスが8000番ポートを使用していないか確認
#   sudo lsof -i :8000
# - メモリ不足: Docker のメモリ制限を確認
#   docker system info | grep Memory
```

#### 2. ディスク容量不足

```bash
# Dockerが使用している容量を確認
docker system df

# 不要なイメージ・コンテナを削除
docker system prune -a --volumes
```

#### 3. パーミッションエラー

```bash
# 永続化ディレクトリの所有者を修正
sudo chown -R $USER:$USER /opt/app/
```

### ログの確認方法

```bash
# 全サービスのログをリアルタイム表示
docker compose logs -f

# 特定期間のログを表示（最新100行）
docker compose logs --tail=100

# エラーログのみ抽出
docker compose logs 2>&1 | grep -i error

# ログをファイルに保存
docker compose logs > logs_$(date +%Y%m%d_%H%M%S).txt
```

## セキュリティ設定

### 環境変数のセキュリティ

```bash
# .envファイルの権限を制限
chmod 600 django_api/.env

# Gitに.envファイルが含まれていないことを確認
git status --ignored
```

### イメージの署名と検証

```bash
# Build Provenanceの確認
gh attestation verify oci://ghcr.io/kagiyama-baking/kawashiro-server/django-api:staging \
  --owner kagiyama-baking

# 脆弱性スキャン
trivy image ghcr.io/kagiyama-baking/kawashiro-server/django-api:staging
```

## 開発者向けガイド

### 開発環境のセットアップ

```bash
# 開発用ブランチの作成
git checkout -b feature/your-feature-name

# 開発環境の起動
docker compose up -d
```

### テストの実行

```bash
# Django APIテスト
cd django_api
uv run pytest tests/ -v --tb=short \
  --cov=user --cov=core --cov=integrations --cov=features \
  --cov-report=term-missing -m "not e2e"
```

### コーディング規約

- Dockerfile はベストプラクティスに従う
- 環境変数は大文字とアンダースコア
- ドキュメントは日本語で記述

## 技術スタック

### バックエンド

- **Django**: Python Web フレームワーク
- **Django REST Framework**: REST API 構築
- **Gunicorn**: WSGI HTTP サーバー（本番環境）
- **SQLite**: 軽量データベース（Django API 用）

### インフラ・DevOps

- **Docker & Docker Compose**: コンテナ化とオーケストレーション
- **Traefik**: リバースプロキシ（internal.kagiyama.net で管理）
- **GitHub Actions**: CI/CD パイプライン
- **GitHub Container Registry**: コンテナイメージレジストリ

### ツール・ユーティリティ

- **uv**: 高速 Python パッケージマネージャー
- **pytest**: Python テストフレームワーク
- **Ruff**: Python リンター・フォーマッター
- **Trivy**: コンテナセキュリティスキャナー

### 外部サービス連携

- **Microsoft Graph API**: OneDrive/Outlook 連携
- **OpenAI API**: テキスト生成（挨拶機能）
- **気象庁天気予報 API**: 天気予報データ取得
- **Style-BERT-VITS2**: 高品質日本語音声合成エンジン（CUDA 11.8）

## 謝辞

このプロジェクトは以下のオープンソースプロジェクト・サービスを使用しています：

- [Django](https://www.djangoproject.com/) - Python Web フレームワーク
- [Docker](https://www.docker.com/) - コンテナ化プラットフォーム
- [uv](https://github.com/astral-sh/uv) - 高速 Python パッケージマネージャー
- [Style-BERT-VITS2](https://github.com/litagin02/Style-Bert-VITS2) - 高品質日本語音声合成エンジン
- [OpenAI](https://openai.com/) - AI テキスト生成 API

FROM python:3.13-alpine AS base

# リアルタイムでログを見れるように環境変数を指定
ENV PYTHONUNBUFFERED=1

# セキュリティのため、OSパッケージを最新版にアップデート
# ビルド時に --no-cache-filter=base を指定すると常に最新パッケージを取得
RUN apk update && \
    apk upgrade --no-cache && \
    apk add --no-cache \
        ca-certificates \
        tzdata \
        postgresql16-client && \
    rm -rf /var/cache/apk/*

# 作業ディレクトリを設定
WORKDIR /app

# pipを最新版にアップグレードしてからuvをインストール
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir uv

# Python依存関係をインストール（pyproject.tomlから）
# uv pip installでシステムPythonに直接インストール
COPY pyproject.toml ./
RUN mkdir -p scripts && \
    touch scripts/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf scripts

# アプリケーションを実行するためのユーザを作成する
# /backup と /restore はボリュームマウント用ディレクトリ
RUN adduser -D -g backup backup && \
    chown -R backup:backup /app && \
    mkdir -p /backup /restore && \
    chown backup:backup /backup /restore

# ユーザをrootから変更
USER backup

# スクリプトをコピー
COPY --chown=backup:backup scripts/ ./scripts/

# セキュリティヘッダーを設定
ENV PYTHONDONTWRITEBYTECODE=1

# デフォルトコマンド（統合バックアップ）
# 個別実行する場合は以下のように上書き可能:
#   --immich-only: Immich のみバックアップ
#   --django-only: Django のみバックアップ
CMD ["python", "-m", "scripts.backup_all"]

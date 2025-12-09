FROM python:3.13-alpine AS base

# リアルタイムでログを見れるように環境変数を指定
ENV PYTHONUNBUFFERED=1

# セキュリティのため、OSパッケージを最新版にアップデート
# curlも追加（ヘルスチェック用）
# libheifも追加（HEIF/HEIC画像形式サポート用）
# ビルド時に --no-cache-filter=base を指定すると常に最新パッケージを取得
RUN apk update && \
    apk upgrade --no-cache && \
    apk add --no-cache \
        ca-certificates \
        tzdata \
        curl \
        libheif && \
    rm -rf /var/cache/apk/*

# Djangoプロジェクトを置くディレクトリをコンテナ上に作成
RUN mkdir /django_api
WORKDIR /django_api

# pipを最新版にアップグレードしてからuvをインストール
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir uv

# Python依存関係をインストール（pyproject.tomlから）
# uv pip installでシステムPythonに直接インストール
# パッケージディレクトリが必要なため、先に作成
COPY pyproject.toml ./
RUN mkdir -p django_api core user onedrive media && \
    touch django_api/__init__.py core/__init__.py user/__init__.py onedrive/__init__.py media/__init__.py && \
    uv pip install --system --no-cache . && \
    uv pip install --system --no-cache pytest pytest-django pytest-cov pytest-mock && \
    rm -rf django_api core user onedrive media

# アプリケーションを実行するためのユーザを作成する（先に作成）
RUN adduser -D -g django django && \
    chown -R django:django /django_api

# ユーザをrootから変更（ファイルコピー前に変更）
USER django

# 必要なアプリケーションファイルのみをコピー
# manage.pyと各アプリケーションディレクトリ
COPY --chown=django:django manage.py .
COPY --chown=django:django django_api ./django_api
COPY --chown=django:django core ./core
COPY --chown=django:django user ./user
COPY --chown=django:django onedrive ./onedrive
COPY --chown=django:django media ./media

# セキュリティヘッダーを設定
ENV PYTHONDONTWRITEBYTECODE=1

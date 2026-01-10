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
RUN mkdir -p django_api core user onedrive outlook media tts msgraph_config msgraph_client weather train greeting llm_config llm_client && \
    touch django_api/__init__.py core/__init__.py user/__init__.py onedrive/__init__.py outlook/__init__.py media/__init__.py tts/__init__.py msgraph_config/__init__.py msgraph_client/__init__.py weather/__init__.py train/__init__.py greeting/__init__.py llm_config/__init__.py llm_client/__init__.py && \
    uv pip install --system --no-cache . && \
    uv pip install --system --no-cache pytest pytest-django pytest-cov pytest-mock && \
    rm -rf django_api core user onedrive outlook media tts msgraph_config msgraph_client weather train greeting llm_config llm_client

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
COPY --chown=django:django outlook ./outlook
COPY --chown=django:django media ./media
COPY --chown=django:django tts ./tts
COPY --chown=django:django msgraph_config ./msgraph_config
COPY --chown=django:django weather ./weather
COPY --chown=django:django train ./train
COPY --chown=django:django greeting ./greeting
COPY --chown=django:django llm_config ./llm_config
COPY --chown=django:django llm_client ./llm_client
COPY --chown=django:django msgraph_client ./msgraph_client

# セキュリティヘッダーを設定
ENV PYTHONDONTWRITEBYTECODE=1

FROM python:3.13-alpine AS base

# リアルタイムでログを見れるように環境変数を指定
ENV PYTHONUNBUFFERED=1

# セキュリティのため、OSパッケージを最新版にアップデート
# curlも追加（ヘルスチェック用）
# libheifも追加（HEIF/HEIC画像形式サポート用）
# OpenSSLパッケージを明示的にアップグレード（CVE-2025-15467, CVE-2025-69419対応）
# zlibを明示的にアップグレード（CVE-2026-22184対応）
# ビルド時に --no-cache-filter=base を指定すると常に最新パッケージを取得
RUN apk update && \
    apk upgrade --no-cache && \
    apk add --no-cache \
        ca-certificates \
        tzdata \
        curl \
        libheif \
        libpq \
        libcrypto3 \
        libssl3 \
        zlib && \
    rm -rf /var/cache/apk/*

# Djangoプロジェクトを置くディレクトリをコンテナ上に作成
RUN mkdir /django_api
WORKDIR /django_api

# pipを最新版にアップグレードしてからuvをインストール
# setuptools内の脆弱性を修正するため、ベンダー化されたパッケージを更新:
# - jaraco.context: GHSA-58pv-8j8x-9vj2 (6.1.0以上に更新)
# - wheel: CVE-2026-24049 (0.46.2以上に更新)
RUN pip install --no-cache-dir --upgrade pip setuptools 'wheel>=0.46.2' && \
    pip install --no-cache-dir uv && \
    SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])") && \
    pip download --no-deps --dest /tmp jaraco.context>=6.1.0 && \
    pip download --no-deps --dest /tmp 'wheel>=0.46.2' && \
    cd "$SITE_PACKAGES/setuptools/_vendor" && \
    rm -rf jaraco.context-*.dist-info jaraco/context.py jaraco/context && \
    python -m zipfile -e /tmp/jaraco*.whl /tmp/jaraco_extract && \
    cp -r /tmp/jaraco_extract/jaraco/context jaraco/ && \
    cp -r /tmp/jaraco_extract/jaraco_context-*.dist-info . && \
    rm -rf wheel-*.dist-info wheel && \
    python -m zipfile -e /tmp/wheel*.whl /tmp/wheel_extract && \
    cp -r /tmp/wheel_extract/wheel . && \
    cp -r /tmp/wheel_extract/wheel-*.dist-info . && \
    rm -rf /tmp/jaraco* /tmp/wheel*

# Python依存関係をインストール（pyproject.tomlから）
# uv pip installでシステムPythonに直接インストール
# パッケージディレクトリが必要なため、先に作成
COPY pyproject.toml ./
RUN mkdir -p django_api core user integrations features health && \
    touch django_api/__init__.py core/__init__.py user/__init__.py integrations/__init__.py features/__init__.py health/__init__.py && \
    uv pip install --system --no-cache . && \
    uv pip install --system --no-cache pytest pytest-django pytest-cov pytest-mock && \
    pip uninstall -y uv && \
    rm -rf django_api core user integrations features health

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
COPY --chown=django:django integrations ./integrations
COPY --chown=django:django features ./features
COPY --chown=django:django health ./health

# セキュリティヘッダーを設定
ENV PYTHONDONTWRITEBYTECODE=1

FROM python:3.13-alpine

# リアルタイムでログを見れるように環境変数を指定
ENV PYTHONUNBUFFERD 1

# セキュリティのため、OSパッケージを最新版にアップデート
# curlも追加（ヘルスチェック用）
RUN apk update && \
    apk upgrade --no-cache && \
    apk add --no-cache \
        ca-certificates \
        tzdata \
        curl && \
    rm -rf /var/cache/apk/*

# Djangoプロジェクトを置くディレクトリをコンテナ上に作成
RUN mkdir /django_api
WORKDIR /django_api

# pipを最新版にアップグレードしてからuvをインストール
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir uv

# Python依存関係をインストール（最新版を取得）
# uv pip installでシステムPythonに直接インストール
COPY pyproject.toml ./
RUN uv pip install --system \
    django \
    djangorestframework \
    drf-spectacular \
    python-dotenv \
    msal

# アプリケーションを実行するためのユーザを作成する（先に作成）
RUN adduser -D -g django django && \
    chown -R django:django /django_api

# ユーザをrootから変更（ファイルコピー前に変更）
USER django

# ローカルのdjango-apiディレクトリをコンテナにコピー（djangoユーザー権限で）
COPY --chown=django:django . .

# セキュリティヘッダーを設定
ENV PYTHONDONTWRITEBYTECODE=1

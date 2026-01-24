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
    rm -rf /tmp/jaraco* && \
    rm -rf wheel-*.dist-info wheel && \
    pip download --no-deps --dest /tmp 'wheel>=0.46.2' && \
    python -m zipfile -e /tmp/wheel*.whl /tmp/wheel_extract && \
    cp -r /tmp/wheel_extract/wheel . && \
    cp -r /tmp/wheel_extract/wheel-*.dist-info . && \
    rm -rf /tmp/wheel*

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

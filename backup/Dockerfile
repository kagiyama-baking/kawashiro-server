FROM python:3.13-alpine

# パッケージのアップデートとアップグレード
# キャッシュバスト用ARG
ARG CACHEBUST=1
RUN apk update && apk upgrade

# 必要なパッケージのインストール
RUN apk add --no-cache \
    postgresql16-client

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係ファイルをコピー
COPY pyproject.toml ./

# Pythonパッケージをインストール
RUN pip install --no-cache-dir requests

# スクリプトをコピー
COPY scripts/ ./scripts/

# デフォルトコマンド
CMD ["python", "/app/scripts/backup_immich.py"]

FROM alpine:latest

# パッケージのアップデートとアップグレード
RUN apk update && apk upgrade

# 必要なパッケージのインストール
RUN apk add --no-cache \
    postgresql16-client \
    curl \
    tar \
    gzip \
    bash \
    findutils

# バックアップスクリプトの実行権限を設定
WORKDIR /scripts

# デフォルトコマンド
CMD ["/bin/bash", "/scripts/backup_immich.sh"]

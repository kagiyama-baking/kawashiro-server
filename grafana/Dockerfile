FROM grafana/grafana:latest AS base

# セキュリティのため、OSパッケージを最新版にアップデート
# ビルド時に --no-cache-filter=base を指定すると常に最新パッケージを取得
USER root
RUN apk update && \
    apk upgrade --no-cache && \
    apk add --no-cache \
        ca-certificates \
        tzdata \
        libcrypto3 \
        libssl3 && \
    rm -rf /var/cache/apk/*

# プロビジョニング設定をコピー
COPY provisioning /etc/grafana/provisioning

USER grafana

EXPOSE 3000

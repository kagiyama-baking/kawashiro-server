FROM nginx:alpine AS base

# セキュリティのため、OSパッケージを最新版にアップデート
# ビルド時に --no-cache-filter=base を指定すると常に最新パッケージを取得
RUN apk update && \
    apk upgrade --no-cache && \
    apk add --no-cache \
        ca-certificates \
        tzdata && \
    rm -rf /var/cache/apk/*

# デフォルトの設定ファイルを削除（ポート80を使用している）
RUN rm -f /etc/nginx/conf.d/default.conf

# 設定をイメージに焼く
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/*.conf /etc/nginx/conf.d/
COPY html/* /usr/share/nginx/html/

# 非rootユーザーで実行するために必要なディレクトリの権限を設定
RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx/conf.d /tmp /var/run
USER nginx

# コンテナがリッスンするポートを指定
EXPOSE 8080

# Nginxを実行
CMD ["nginx", "-g", "daemon off;"]
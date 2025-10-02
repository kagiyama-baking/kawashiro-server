FROM nginx:alpine

# デフォルトの設定ファイルを削除（ポート80を使用している）
RUN rm -f /etc/nginx/conf.d/default.conf

# 設定をイメージに焼く
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/*.conf /etc/nginx/conf.d/
COPY html/* /usr/share/nginx/html/

# nginxユーザーに必要なディレクトリの権限を設定
RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx/conf.d

# 非rootで動かす
USER nginx

# コンテナがリッスンするポートを指定
EXPOSE 8080

# Nginxを実行
CMD ["nginx", "-g", "daemon off;"]
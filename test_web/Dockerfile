FROM nginx:alpine

# 設定をイメージに焼く
COPY conf.d/*.conf /etc/nginx/conf.d/
COPY html/* /usr/share/nginx/html/

# nginxユーザーに必要なディレクトリの権限を設定
RUN touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /var/log/nginx /etc/nginx/conf.d

# 非rootで動かす
USER nginx

# コンテナがリッスンするポートを指定
EXPOSE 8080

# Nginxを実行
CMD ["nginx", "-g", "daemon off;"]
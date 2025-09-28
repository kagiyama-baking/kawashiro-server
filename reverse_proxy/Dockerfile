FROM nginx:alpine

# 設定をイメージに焼く
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/*.conf /etc/nginx/conf.d/
COPY html/* /usr/share/nginx/html/

# 非rootで動かす
USER nginx

# コンテナがリッスンするポートを指定
EXPOSE 8080

# Nginxを実行
CMD ["nginx", "-g", "daemon off;"]
FROM nginx:alpine

# HTMLファイルをコピー
COPY index.html /usr/share/nginx/html/

# ポート80を公開
EXPOSE 80

# Nginxを実行
CMD ["nginx", "-g", "daemon off;"]
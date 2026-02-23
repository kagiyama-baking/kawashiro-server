FROM grafana/loki:latest

# カスタム設定ファイルをコピー
COPY loki.yml /etc/loki/loki.yml

EXPOSE 3100

CMD ["-config.file=/etc/loki/loki.yml"]

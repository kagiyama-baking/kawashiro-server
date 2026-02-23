FROM grafana/promtail:latest

# カスタム設定ファイルをコピー
COPY promtail.yml /etc/promtail/promtail.yml

EXPOSE 9080

CMD ["-config.file=/etc/promtail/promtail.yml"]

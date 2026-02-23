FROM prom/prometheus:latest

# カスタム設定ファイルをコピー
COPY prometheus.yml /etc/prometheus/prometheus.yml

# 非rootユーザーで実行（公式イメージのデフォルト）
USER nobody

EXPOSE 9090

CMD ["--config.file=/etc/prometheus/prometheus.yml", \
     "--storage.tsdb.path=/prometheus", \
     "--storage.tsdb.retention.time=30d", \
     "--web.console.libraries=/usr/share/prometheus/console_libraries", \
     "--web.console.templates=/usr/share/prometheus/consoles"]

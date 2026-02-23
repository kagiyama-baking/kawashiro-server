FROM prom/prometheus:latest

# ※ Prometheus公式イメージはbusyboxベース（パッケージマネージャなし）のため
#    apk upgrade によるOSパッケージ更新は不可。
#    脆弱性対応はベースイメージの更新（:latest タグの再pull）で行う。

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

FROM grafana/loki:latest

# ※ Loki公式イメージはscratchベース（シェル・パッケージマネージャなし）のため
#    apk upgrade によるOSパッケージ更新は不可。
#    脆弱性対応はベースイメージの更新（:latest タグの再pull）で行う。

# カスタム設定ファイルをコピー
COPY loki.yml /etc/loki/loki.yml

EXPOSE 3100

CMD ["-config.file=/etc/loki/loki.yml"]

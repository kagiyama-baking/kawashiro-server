FROM grafana/promtail:latest

# ※ Promtail公式イメージはscratchベース（シェル・パッケージマネージャなし）のため
#    apk upgrade によるOSパッケージ更新は不可。
#    脆弱性対応はベースイメージの更新（:latest タグの再pull）で行う。

# カスタム設定ファイルをコピー
COPY promtail.yml /etc/promtail/promtail.yml

EXPOSE 9080

CMD ["-config.file=/etc/promtail/promtail.yml"]

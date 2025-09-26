# Nginx リバースプロキシ

このディレクトリには、Docker で動作する Nginx リバースプロキシサーバーの設定が含まれています。

## 構成

```
reverse_proxy/
├── Dockerfile          # Nginxコンテナのビルド設定
├── docker-compose.yml  # Docker Composeの設定
├── nginx.conf          # Nginxのメイン設定ファイル
├── conf.d/            # サーバー別の設定ファイル
│   └── default.conf   # デフォルトのサーバー設定
└── .dockerignore      # Dockerビルド時の除外ファイル
```

## 使用方法

### 起動

```bash
cd reverse_proxy
docker compose up -d
```

### 停止

```bash
docker compose down
```

### ログの確認

```bash
docker compose logs -f nginx-proxy
```

### 設定の再読み込み

```bash
docker compose exec nginx-proxy nginx -s reload
```

## 設定のカスタマイズ

### 新しいプロキシ先の追加

`conf.d/default.conf`内のコメントアウトされた例を参考に、プロキシ先を追加できます：

```nginx
location /app {
    proxy_pass http://your-app:3000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### HTTPS 対応

1. SSL 証明書を`ssl/`ディレクトリに配置
2. `docker-compose.yml`のポートとボリュームのコメントアウトを解除
3. `conf.d/`に新しいサーバー設定を追加

## ヘルスチェック

リバースプロキシの状態は以下のエンドポイントで確認できます：

```bash
curl http://localhost/health
```

## ネットワーク

このリバースプロキシは`kawashiro-proxy-network`という名前の Docker ネットワークを使用します。
他のコンテナをこのネットワークに接続することで、内部通信が可能になります。

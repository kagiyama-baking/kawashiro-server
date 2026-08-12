# Style-BERT-VITS2 API（sbv2_api）

[Style-BERT-VITS2](https://github.com/litagin02/Style-Bert-VITS2) による日本語音声合成を HTTP API として提供する、Kawashiro Server の内部サービスです。

## 概要

- **FastAPI の薄いラッパー**（`server.py` 1 ファイル）。推論エンジンは `style-bert-vits2==2.5.0` に委譲します
- **起動時に全モデルをプリロード**します。lifespan で日本語 BERT（`ku-nlp/deberta-v2-large-japanese-char-wwm`）をロードした後、`model_assets/` 配下の全 TTS モデルを読み込むため、初回リクエストのレイテンシがありません。プリロードに失敗したモデルは警告ログを残してスキップされ、起動自体は継続します
- **CPU 推論がデフォルト**です。GPU 非搭載ホストでもそのまま動作し、NVIDIA GPU ホストではビルド引数と環境変数で CUDA に切り替えます（[CPU / GPU 切替](#cpu--gpu-切替)）
- **内部サービスのため認証・CORS はありません**。コンテナネットワーク内からのみアクセスされる前提です。Django からは `django_api/integrations/tts/client.py` が `TTS_SERVICE_URL`（既定 `http://sbv2-api:5000`）に対して `POST /synthesize` を呼びます

デプロイ全般は [../docs/deployment.md](../docs/deployment.md)、開発環境全般は [../docs/development.md](../docs/development.md) を参照してください。

## API エンドポイント

| メソッド   | パス                          | 説明                                                                      |
| ---------- | ----------------------------- | ------------------------------------------------------------------------- |
| `GET`      | `/health`                     | ヘルスチェック。`{"status": "healthy", "models_available": N}` を返す      |
| `GET`      | `/models`                     | モデル一覧。`{"models": [...], "default": <config の default_model>}`      |
| `GET`      | `/models/{model_name}/styles` | 指定モデルのスタイル一覧。`{"model": ..., "styles": [...]}`                |
| `GET`      | `/synthesize`                 | 音声合成（クエリパラメータ）                                              |
| `POST`     | `/synthesize`                 | 音声合成（JSON ボディ）。パラメータは GET と同一                          |

`/health` は**モデルが 0 件でも 200 を返します**（コンテナの生死判定用）。実際に合成可能かは `models_available` の値で判断してください。

### 合成パラメータ

| パラメータ      | 型     | 必須 | 既定値      | 範囲 / 制約            | 説明                                             |
| --------------- | ------ | ---- | ----------- | ---------------------- | ------------------------------------------------ |
| `text`          | string | ✅   | -           | `max_length` 以下      | 読み上げるテキスト。超過すると 400                |
| `model`         | string | -    | 既定モデル  | `^[a-zA-Z0-9_\-]+$`    | モデル名。省略時は `config.yml` の解決結果        |
| `style`         | string | -    | `Neutral`   | モデルが持つスタイル名 | 未知のスタイルは 400（利用可能な一覧を返す）      |
| `style_weight`  | float  | -    | `1.0`       | 0.0 〜 10.0            | スタイルの強さ                                    |
| `speed`         | float  | -    | `1.0`       | 0.5 〜 2.0             | 話速。内部では `length = 1.0 / speed` に変換      |
| `sdp_ratio`     | float  | -    | `0.2`       | 0.0 〜 1.0             | SDP の比率（抑揚のゆらぎ）                        |
| `noise_scale`   | float  | -    | `0.6`       | 0.0 〜 1.0             | サンプリングノイズ                                |
| `noise_scale_w` | float  | -    | `0.8`       | 0.0 〜 1.0             | 音素長のノイズ                                    |
| `format`        | string | -    | `wav`       | `wav` / `mp3` / `ogg`  | 出力フォーマット。範囲外は 422                    |

成功時は音声バイナリを返し、レスポンスヘッダに `X-Model`（使用モデル名）と `X-Style`（使用スタイル名）が付きます。

| ステータス | 発生条件                                                                       |
| ---------- | ------------------------------------------------------------------------------ |
| `400`      | テキスト長超過 / 未知のスタイル / モデル名が命名規則違反（パストラバーサル防止） |
| `404`      | モデルディレクトリまたは必須ファイル（`config.json` 等）が存在しない            |
| `422`      | `format` などの値がバリデーション範囲外                                        |
| `503`      | 既定モデルを解決できない（`default_model` 未設定かつモデル 0 件）              |
| `500`      | 推論・フォーマット変換の失敗。詳細はログのみに出力し、レスポンスには含めない    |

### curl 例

```bash
# ホストから（docker-compose.yml でポート 5000 を公開）
curl -X POST http://localhost:5000/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "こんにちは、鍵山です。", "style": "Neutral", "speed": 1.1, "format": "mp3"}' \
  --output hello.mp3
```

## モデル資産の配置

学習済みモデルはホストの `/opt/app/sbv2-api/model_assets/` に置き、コンテナへ `/app/model_assets` として**読み取り専用**でマウントされます（`docker-compose.yml`）。モデルはリポジトリには含めません。

```
/opt/app/sbv2-api/model_assets/
└── <モデル名>/
    ├── config.json          # 必須。これが無いディレクトリは一覧に出ない
    ├── style_vectors.npy    # 必須
    └── *.safetensors        # 必須。複数ある場合は mtime が最新のものを採用
```

- **モデル名 = ディレクトリ名**です。`^[a-zA-Z0-9_\-]+$`（英数字・ハイフン・アンダースコア）のみ許可され、それ以外は 400 になります
- 一覧は `config.json` を持つディレクトリのみを**名前順ソート**して返します。`config.json` が無いディレクトリは黙って無視されます
- `config.json` はあるが `style_vectors.npy` や `*.safetensors` が欠けている場合、一覧には出るものの読み込み時に 404 になります（起動時のプリロードでは警告ログのみ）
- **既定モデル**は `config.yml` の `default_model` が優先され、`null` の場合は名前順で先頭のモデルが使われます
- **モデル 0 件**の場合、`/health` と `/models` は 200 を返しますが、`model` を省略した `/synthesize` は 503（`No models available`）になります。モデルを追加したら `docker compose restart sbv2-api` でプリロードし直してください

## 環境変数

| 変数名                   | 既定値                                            | 説明                                              |
| ------------------------ | ------------------------------------------------- | ------------------------------------------------- |
| `SBV2_CONFIG_PATH`       | `/app/config.yml`                                 | 設定ファイルのパス。存在しない場合は既定値で動作   |
| `SBV2_MODEL_ASSETS_PATH` | `/app/model_assets`                               | モデル資産のルートディレクトリ                     |
| `SBV2_BERT_MODEL_PATH`   | `/app/bert/deberta-v2-large-japanese-char-wwm`    | 日本語 BERT のパス（イメージに同梱済み）           |
| `SBV2_DEVICE`            | `cpu`                                             | 推論デバイス（`cpu` / `cuda` / `mps` 等）          |

`SBV2_DEVICE=cpu` のときは、BERT モデルと TTS モデルのパラメータ・バッファを float32 に変換します（float16 のまま CPU 推論すると失敗するため）。

## CPU / GPU 切替

PyTorch のバリアントは**ビルド引数**で決まります。実行時に切り替えることはできないため、GPU 化にはリビルドが必要です。

| ビルド引数       | 既定値  | GPU 構成 | 説明                                                       |
| ---------------- | ------- | -------- | ---------------------------------------------------------- |
| `TORCH_VARIANT`  | `cpu`   | `cu121`  | `https://download.pytorch.org/whl/${TORCH_VARIANT}` を使用 |
| `TORCH_VERSION`  | `2.3.1` | `2.5.1`  | torch / torchaudio のバージョン                             |

`docker-compose.gpu.yml` が上記のビルド引数に加えて `SBV2_DEVICE=cuda`、`NVIDIA_VISIBLE_DEVICES=all`、NVIDIA GPU 1 枚の予約（`deploy.resources.reservations.devices`）を設定します。

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build sbv2-api
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

毎回 `-f` を並べる代わりに、リポジトリルートの `.env` に `COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml` を設定しておく方法もあります（開発機ではこの方式を採用）。

> **Note:** `style-bert-vits2` の公式推奨は torch `<2.4` ですが、GPU 構成では RTX 4080 上で 2.5.1 の動作・音質・速度を実測検証済みです。問題が起きた場合は `docker-compose.gpu.yml` の `TORCH_VERSION` 行を削除すれば既定の 2.3.1 に戻ります。

## 音声フォーマット

| フォーマット | Content-Type  | 生成方法                                          |
| ------------ | ------------- | ------------------------------------------------- |
| `wav`        | `audio/wav`   | 推論結果をそのまま出力（変換なし）                 |
| `mp3`        | `audio/mpeg`  | ffmpeg で変換（128kbps / モノラル）                |
| `ogg`        | `audio/ogg`   | ffmpeg で変換（モノラル）                          |

mp3 / ogg は WAV をパイプ経由で ffmpeg に渡して変換します（タイムアウト 30 秒）。ffmpeg はイメージに同梱済みです。変換対象フォーマットはホワイトリストで検証しており、変換の失敗・タイムアウトは 500 になります。

## 開発とテスト

テストは `style_bert_vits2` を `sys.modules` に差し替えてスタブ化するため、**torch も学習済みモデルも不要**です。`pyproject.toml` の依存はテスト実行に必要な軽量パッケージのみで、実行時依存（`style-bert-vits2` / `torch` / `transformers`）は CPU/CUDA バリアントを選ぶ都合上 Dockerfile 側でインストールします。

`tests/conftest.py` の `sbv2_stubs` フィクスチャが `style_bert_vits2.constants` / `.nlp` / `.tts_model` のスタブを注入し、`server_factory` フィクスチャが `tmp_path` にダミーのモデル資産と `config.yml` を作った上で環境変数を設定し、`server` モジュールをテストごとにフレッシュにインポートします。

```bash
cd sbv2_api

uv sync                    # 軽量依存のみをインストール
uv run pytest tests/ -v    # テスト実行

uv run ruff check .            # リンタ
uv run ruff format --check .   # フォーマット確認（CI 相当）
uv run ruff format .           # フォーマット適用
```

`docker-compose.yml` は開発用に `server.py` をコンテナへマウントしているため、コード変更はリビルドなしで反映されます（反映には `docker compose restart sbv2-api` が必要）。

## config.yml

```yaml
# デフォルトモデル（nullの場合は最初に見つかったモデル）
default_model: null

# テキスト最大文字数
max_length: 500
```

| キー            | 既定値 | 説明                                                                          |
| --------------- | ------ | ----------------------------------------------------------------------------- |
| `default_model` | `null` | `model` 省略時に使うモデル名。`null` なら名前順で先頭のモデル                   |
| `max_length`    | `500`  | `text` の最大文字数。超過時は 400。設定ファイルが無い場合もこの値が使われる     |

`config.yml` は `:ro` でマウントされるため、変更後は `docker compose restart sbv2-api` で再読み込みしてください（設定はモジュール読み込み時に一度だけ評価されます）。なお `GET /models` の `default` フィールドは `default_model` の設定値をそのまま返すため、未設定時は実効値ではなく `null` が返ります。

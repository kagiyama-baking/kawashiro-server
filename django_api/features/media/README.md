# Media — 画像変換・ZIP→PDF

画像ファイルの形式変換と、ZIP 内画像の PDF 化を行う機能です。実装は `views.py`（`ZipToPdfView` / `ImageConvertView`）の 2 クラスのみで、モデル・シリアライザは持ちません。

**本ファイルは media 機能の制限値の唯一の正（SSOT）です。** 制限値を変更した場合は `views.py` のクラス定数と本ファイルを必ず同時に更新してください。

- 認証: **必須**（`IsAuthenticated`）。`Authorization: Token <key>` によるトークン認証、またはセッション認証
- リクエスト形式: 両エンドポイントとも `multipart/form-data`
- レスポンス: 成功時はバイナリ（`application/pdf` / `image/*`）、失敗時は `{"error": "..."}` の JSON
- 利用箇所: フロントエンドの `/media` 画面（`frontend/src/features/media/`）

## API リファレンス

### POST `/media/zip-to-pdf/`

ZIP 内の画像をファイル名の昇順に並べて 1 つの PDF にまとめます。

| パラメータ | 必須 | 型 | 説明 |
| ---------- | ---- | -- | ---- |
| `file`     | 必須 | binary | 画像を含む ZIP ファイル |

| レスポンス | 内容 |
| ---------- | ---- |
| 200 | `application/pdf`。`Content-Disposition` はアップロードした ZIP 名の拡張子を `.pdf` に置換したもの（RFC 6266 / 5987 形式で `filename` と `filename*` を併記するため、日本語ファイル名も保持される） |
| 400 | ファイル未指定 / ZIP として不正 / 画像 0 件 / ファイル数・合計サイズ超過 / 画像形式不正 |
| 401 | 未認証 |
| 413 | 単一画像のメガピクセル数が上限超過、または Pillow の Decompression Bomb 検出 |
| 503 | 変換中の `MemoryError`（本番の `mem_limit` 512MiB に起因） |

### POST `/media/convert-image/`

単一画像の形式を変換します。

| パラメータ      | 必須 | 型 | 説明 |
| --------------- | ---- | -- | ---- |
| `file`          | 必須 | binary | 変換する画像ファイル |
| `output_format` | 必須 | string | `jpg` / `png` / `webp` / `tiff`。大文字で送っても内部で小文字化される |
| `quality`       | 任意 | integer | JPEG 品質 1〜100（既定 85）。**`output_format=jpg` のときのみ読み取られ、他形式では検証もされず完全に無視される** |

| レスポンス | 内容 |
| ---------- | ---- |
| 200 | `image/jpeg` / `image/png` / `image/webp` / `image/tiff`。ファイル名は `YYYYMMDD.WxH.ext` |
| 400 | ファイル未指定 / サイズ超過 / `output_format` 未指定・非対応 / `quality` 不正 / 画像として読めない |
| 401 | 未認証 |

## 制限値一覧

| 定数 | 値 | 適用先 | 超過時 |
| ---- | -- | ------ | ------ |
| `ZipToPdfView.MAX_FILES` | **1000** | ZIP 内の**全エントリ数**（画像以外・ディレクトリも計上） | 400 |
| `ZipToPdfView.MAX_TOTAL_SIZE` | **1GB**（1073741824 B） | ZIP 内全エントリの**展開後**サイズ合計（`ZipInfo.file_size` の総和） | 400 |
| `ZipToPdfView.MAX_PER_IMAGE_MEGAPIXELS` | **100.0 MP** | 画像 **1 枚あたり**の幅 × 高さ。合計ではない | 413 |
| `ImageConvertView.MAX_FILE_SIZE` | **50MB**（52428800 B） | アップロードファイルのバイト数 | 400 |
| `ImageConvertView.MIN/MAX_JPEG_QUALITY` | **1〜100**（既定 `DEFAULT_JPEG_QUALITY` = 85） | `output_format=jpg` の `quality` | 400 |
| `Image.MAX_IMAGE_PIXELS`（Pillow 既定） | 89478485 px（約 89.5MP） | 全画像。超過で警告、その 2 倍で `DecompressionBombError` | 413（zip-to-pdf のみ） |

補足:

- **zip-to-pdf にファイルサイズ上限はない。** 制限は「展開後の合計 1GB」であり、アップロード ZIP 自体のバイト数はチェックされない。実効上限は下記 nginx の 1100m
- **convert-image にメガピクセル上限はない。** ガードは 50MB のバイト数のみ。50MB に収まる高解像度 PNG が Pillow の Decompression Bomb に達した場合、専用ハンドラがないため 413 ではなく汎用の 400 になる
- `MAX_PER_IMAGE_MEGAPIXELS` が 100MP なのは、PNG/WEBP を RGB 展開したときのメモリピーク（100MP ≒ 300MB）を本番 `mem_limit` 512MiB に収めるためのガード（`views.py` のコメント参照）

## 変換の内部挙動

**ZIP 内の対象拡張子**: `.jpg` `.jpeg` `.png` `.webp` の 4 種のみ。TIFF や HEIC は ZIP→PDF では対象外。`__MACOSX/` 配下、パスセグメントに `..` を含むもの、絶対パス、ディレクトリ（`/` 終端）は除外され、残りをファイル名昇順にソートして PDF のページ順とする。

**JPEG はパススルー**: `.jpg` / `.jpeg` は img2pdf にバイト列のまま渡され、**再エンコードされない**。画質劣化がなく、Pillow によるピクセル展開も発生しないため、漫画スキャンのような大量ページでもメモリを消費しない。

**PNG/WEBP は再エンコード**: Pillow で 1 枚ずつ開き、JPEG（quality=90）に変換したバイト列だけを保持する。`RGBA` / `LA` は白背景に合成、それ以外の非 RGB モードは `convert("RGB")`。PIL Image を全ページ分同時に保持しない実装で OOM を回避している。

**メガピクセル事前検査**: PDF 生成前に全画像のヘッダのみを読んで `size` を取得し、上限超過があればその時点で 413 を返す。ピクセルデータをロードしないため検査自体は軽量。

**convert-image の入力形式**: `views.py` の docstring と OpenAPI 記述は `jpg / png / webp / tiff / heif / heic / psd / dng` を挙げるが、**コード上に入力形式の allowlist は存在しない**。実際には Pillow（+ `pillow_heif` による HEIF/HEIC オープナ登録）が開ける形式なら通る。上記 8 種はテストで担保された動作確認済みの範囲と解釈すること。

**出力ファイル名の日付**: EXIF の `DateTimeOriginal`(36867) → `DateTime`(306) の順に探し、見つかればその日付。いずれもなければ `settings.TIME_ZONE`（`Asia/Tokyo`）での現在日付を `YYYYMMDD` として使う。

## エラーレスポンス例

```jsonc
// 400: ZIP 内に対象画像がない
{ "error": "ZIPファイル内に画像が見つかりませんでした" }

// 400: ファイル数超過
{ "error": "ZIPファイル内のファイル数が多すぎます（最大1000件まで）" }

// 400: convert-image のサイズ超過
{ "error": "ファイルサイズが大きすぎます（最大50MBまで）" }

// 413: 単一画像のメガピクセル超過
{ "error": "ZIP内の画像 'scan/001.png' の解像度が大きすぎます （120.5メガピクセル, 1枚あたり上限 100メガピクセル）。サイズを小さくしてから再試行してください。" }

// 503: 変換中のメモリ不足
{ "error": "サーバーのメモリが不足しました。画像の枚数を減らすか、解像度を下げて再試行してください" }
```

内部例外の詳細はログにのみ記録し、クライアントには汎用メッセージ `画像の処理中にエラーが発生しました` を返す（情報漏洩対策）。

## 経路上の制限

フロントエンド経由の呼び出しは nginx の `/api/` を通って Django に到達する（`frontend/nginx.conf`）。

| 経路 | 実効上限 | 出典 |
| ---- | -------- | ---- |
| `/api/` 経由（フロント画面・本番） | リクエストボディ **1100MB**、応答待ち **120 秒** | `client_max_body_size 1100m` / `proxy_read_timeout 120s` |
| Django へ直接（`localhost:8000`） | 上記の適用なし。アプリ側の制限値のみ | — |

1100m は zip-to-pdf の「展開後 1GB」をアップロード時に通せるよう余裕を持たせた値。ZIP は圧縮されているため通常これに当たることはないが、**超過時に返るのは Django の JSON ではなく nginx の 413 HTML** である点に注意。同様に、大量ページの変換が 120 秒を超えると nginx 側でタイムアウトする（Django の処理自体には時間制限がない）。

## curl 例

```bash
# ZIP → PDF
curl -X POST http://localhost:8000/media/zip-to-pdf/ \
  -H "Authorization: Token <YOUR_TOKEN>" \
  -F "file=@manga.zip" \
  -o manga.pdf

# 画像形式変換（PNG → JPEG, 品質 90）
curl -X POST http://localhost:8000/media/convert-image/ \
  -H "Authorization: Token <YOUR_TOKEN>" \
  -F "file=@photo.png" \
  -F "output_format=jpg" \
  -F "quality=90" \
  -OJ
```

# Frontend

鍵山製パンWebApp のフロントエンドです。React SPA として構築されています。

## 技術スタック

| カテゴリ         | 技術                                |
| ---------------- | ----------------------------------- |
| フレームワーク   | React 19 + Vite                     |
| 言語             | TypeScript                          |
| スタイリング     | Tailwind CSS v4 + shadcn/ui         |
| 状態管理         | Zustand                             |
| HTTP クライアント | ky                                  |
| ルーティング     | React Router v7                     |
| テスト           | Vitest + React Testing Library      |
| E2E テスト       | Playwright                          |
| PDF 処理         | pdf.js（表示）+ pdf-lib（編集出力） |
| パッケージ管理   | pnpm（`packageManager` で 10.32.1 に固定・corepack 前提）|
| 本番配信         | nginx（マルチステージ Docker ビルド）|

> **Note:** pnpm のバージョンは `package.json` の `packageManager` で固定しています。
> pnpm 11 では `onlyBuiltDependencies` が無視され msw のビルドが失敗するため、
> `corepack enable` を実行し固定バージョンを使用してください。

## 画面構成

| パス        | 画面               | 説明                                       |
| ----------- | ------------------ | ------------------------------------------ |
| `/login`    | ログイン           | メールアドレス + パスワードでToken認証     |
| `/`         | ホーム             | バナー + メニューカード                    |
| `/tts`      | テキスト読み上げ   | テキスト入力 → 音声合成 → 再生/ダウンロード |
| `/talk`     | チャット（履歴あり）| 2 ペイン UI（左 = セッション一覧、右 = メッセージ）。プリセット選択して新規セッション作成、過去会話を引き継いだ複数ターン会話、編集再送、音声個別/一括 再生・DL・削除、LLM タイトル自動生成。モバイルではドロワー化、iOS Safari の autoplay にも対応 |
| `/media`    | メディア変換       | 画像フォーマット変換 / ZIP→PDF変換         |
| `/pdf-edit` | PDF編集            | PDF をブラウザ内で編集（サーバー送信なし）。サムネイル一覧のドラッグ&ドロップ並べ替え、複数選択してページ削除・左右分割・トリミング、undo/redo（Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y）、編集結果を pdf-lib で書き出しダウンロード。ページ本体は `React.lazy` による遅延ロード |

## セットアップ

### 1. 依存関係のインストール

```bash
pnpm install
```

### 2. 開発サーバーの起動

```bash
pnpm dev
```

`http://localhost:5173` でアクセスできます。
API リクエストは Vite proxy 経由で `http://localhost:8000` に転送されます。

### 3. バックエンド API の起動

別ターミナルで Django API を起動してください：

```bash
docker compose up django-api
```

## コマンド一覧

```bash
# 開発サーバー起動
pnpm dev

# 本番ビルド
pnpm build

# ESLint
pnpm lint

# Prettier フォーマット
pnpm format
pnpm format:check

# TypeScript 型チェック
pnpm type-check

# ユニットテスト
pnpm test          # watchモード
pnpm test:ci       # CI用（カバレッジ付き）

# E2E テスト（初回は pnpm exec playwright install chromium が必要）
pnpm test:e2e      # ヘッドレス
pnpm test:e2e:ui   # UI モード
```

## テストの実態

- **Vitest**: カバレッジ計測対象は `src/stores/**`・`src/lib/**`・`src/components/auth/**` に限定
  （`chat-store.ts` と `lib/pdf/pdf-worker.ts` は除外）。閾値は lines 80%。
- **Playwright**: `e2e/` に 4 本（login / media / navigation / tts）。
  API は `page.route` でモックするためバックエンド起動は不要。**CI では実行されない**
  （手動実行のみ）。実行前に `pnpm exec playwright install chromium` が必要。

## API 接続

| 環境   | 方式                                              |
| ------ | ------------------------------------------------- |
| 開発   | Vite proxy（`/api/` → `http://localhost:8000/`）  |
| 本番   | nginx proxy（`/api/` → `http://django-api:8000/`）|

両環境とも同一オリジンで動作するため CORS 設定は不要です。
接続先は `api-client.ts` が `window.location.origin + '/api'` で決定する固定値で、
環境変数による切り替えはありません。
nginx 側は大容量 ZIP アップロードに対応するため `client_max_body_size 1100m` を設定しています。

## テーマ

- プライマリカラー: `#316745`（ダークグリーン）
- 常時ダークモード
- タイトルフォント: Kaisei Opti（Google Fonts）

## ディレクトリ構成

```
frontend/
├── src/
│   ├── App.tsx                  # ルーティング定義
│   ├── components/
│   │   ├── ui/                  # shadcn/ui コンポーネント
│   │   ├── layout/              # AppLayout, Sidebar
│   │   ├── audio/               # AudioPlayer, AudioDownload
│   │   ├── auth/                # ProtectedRoute
│   │   └── common/              # LoadingButton, ErrorMessage
│   ├── features/
│   │   ├── home/                # ホーム画面
│   │   ├── login/               # ログイン画面
│   │   ├── tts/                 # テキスト読み上げ
│   │   ├── talk/                # チャット履歴 UI
│   │   │   ├── ChatPage.tsx              # 2 ペイン構成（sidebar + main）
│   │   │   ├── SessionSidebar.tsx        # 履歴一覧 + モバイルドロワー
│   │   │   ├── SessionListItem.tsx       # タイトル / 日時 / サイズ / 削除
│   │   │   ├── NewSessionDialog.tsx      # プリセット選択モーダル
│   │   │   ├── SessionTitleEditor.tsx    # タイトルのインライン編集
│   │   │   ├── ChatThreadView.tsx        # メッセージ一覧 + 入力欄 + ツールバー
│   │   │   ├── ChatMessageItem.tsx       # メッセージ + 編集再送 + 音声 UI
│   │   │   ├── ChatInputForm.tsx         # 送信 / 停止 (キャンセル) ボタン
│   │   │   ├── AudioBundlePlay.tsx       # 一括再生（4 状態, iOS Safari 対応）
│   │   │   └── AudioBundleDownload.tsx   # 一括 DL（WAV を 1 秒無音入りで結合）
│   │   ├── media/               # メディア変換
│   │   └── pdf-edit/            # PDF編集（React.lazy 遅延ロード）
│   │       ├── PdfEditPage.tsx           # ページ本体
│   │       ├── components/               # アップローダ / サムネイル格子(DnD) /
│   │       │                             # ツールバー / トリミングダイアログ / DL ボタン
│   │       └── hooks/                    # usePdfDocument / useHighResPreview /
│   │                                     # useEditorKeybindings
│   ├── lib/
│   │   ├── api-client.ts        # ky インスタンス（Auth自動付与）
│   │   ├── api/                 # API 関数（auth, tts, talk, media）
│   │   ├── audio/               # concat / bundleLoader（音声結合・取得）
│   │   ├── format/              # bytes ヘルパ
│   │   └── pdf/                 # pdf.js 読込/描画・pdf-lib 編集出力・
│   │                            # Worker 設定・出力ファイル名
│   ├── stores/                  # Zustand ストア（auth, tts, chat, pdf-edit）
│   └── types/                   # TypeScript 型定義（auth, media, pdf-edit, talk, tts）
├── tests/                       # Vitest ユニットテスト
├── e2e/                         # Playwright E2E テスト
├── Dockerfile                   # マルチステージビルド（node → nginx）
├── nginx.conf                   # SPA + API プロキシ設定
└── public/
    └── banner.jpg               # ホームバナー画像（.gitignore済み）
```

## バナー画像の差し替え

`public/banner.jpg` に画像を配置するとホーム画面のバナーに表示されます。
このファイルは `.gitignore` で除外されているため、各環境で個別に設定してください。

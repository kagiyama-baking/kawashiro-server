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
| パッケージ管理   | pnpm                                |
| 本番配信         | nginx（マルチステージ Docker ビルド）|

## 画面構成

| パス        | 画面               | 説明                                       |
| ----------- | ------------------ | ------------------------------------------ |
| `/login`    | ログイン           | メールアドレス + パスワードでToken認証     |
| `/`         | ホーム             | バナー + メニューカード                    |
| `/tts`      | テキスト読み上げ   | テキスト入力 → 音声合成 → 再生/ダウンロード |
| `/generate` | テキスト生成読み上げ | プリセット選択 → LLM生成 → TTS再生        |
| `/media`    | メディア変換       | 画像フォーマット変換 / ZIP→PDF変換         |

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

# E2E テスト
pnpm test:e2e      # ヘッドレス
pnpm test:e2e:ui   # UI モード
```

## API 接続

| 環境   | 方式                                              |
| ------ | ------------------------------------------------- |
| 開発   | Vite proxy（`/api/` → `http://localhost:8000/`）  |
| 本番   | nginx proxy（`/api/` → `http://django-api:8000/`）|

両環境とも同一オリジンで動作するため CORS 設定は不要です。

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
│   │   ├── generate/            # テキスト生成読み上げ
│   │   └── media/               # メディア変換
│   ├── lib/
│   │   ├── api-client.ts        # ky インスタンス（Auth自動付与）
│   │   └── api/                 # API 関数（auth, tts, generate, media）
│   ├── stores/                  # Zustand ストア（auth, tts）
│   └── types/                   # TypeScript 型定義
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

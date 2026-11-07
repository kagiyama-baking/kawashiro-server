# Frontend

鍵山製パンWebApp のフロントエンドです。React SPA として構築されています。

## 技術スタック

| カテゴリ         | 技術                                |
| ---------------- | ----------------------------------- |
| フレームワーク   | React 19 + Vite                     |
| 言語             | TypeScript                          |
| スタイリング     | Tailwind CSS v4 + shadcn/ui         |
| 書体             | Murecho + IBM Plex Sans（fontsource で同梱）|
| 状態管理         | Zustand                             |
| チャット UI      | assistant-ui（`useExternalStoreRuntime`）+ react-markdown（remark-gfm, remark-breaks）|
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
| `/`         | ホーム             | 各機能へのメニューカード                   |
| `/tts`      | テキスト読み上げ   | テキスト入力 → 音声合成 → 再生/ダウンロード |
| `/talk/:sessionId?` | チャット（履歴あり）| ChatGPT 風の 1 カラム。新規チャットで Talk 設定とシーン（任意）を選ぶ。応答の逐次表示と Markdown、停止、編集、再生成、音声の個別/一括 再生・DL・削除、LLM タイトル自動生成。一覧はサイドバー（モバイルはドロワー）。詳細は「[チャット](#チャット)」 |
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
  （`lib/pdf/pdf-worker.ts` は除外）。閾値は lines 80%。
  `tests/features/talk/` は実際の assistant-ui の runtime を動かして確かめる。
- **Playwright**: `e2e/` に 5 本（login / media / navigation / talk / tts）。
  API は `page.route` でモックするためバックエンド起動は不要。**CI では実行されない**
  （手動実行のみ）。実行前に `pnpm exec playwright install chromium` が必要。
  `route.fulfill` の本文は一括送信のみなので、`talk.spec.ts` はメッセージの送信と編集だけ
  `fetch` を差し替えて SSE を 1 イベントずつ流す。
  `reuseExistingServer: true` なので、5173 番で別のチェックアウトの dev サーバーが
  動いていると、そちらのコードに対してテストが走る点に注意。

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

kagiyama.net の暗色テーマに揃えた**ダーク固定**のデザインです。

| 項目         | 内容                                                                                         |
| ------------ | -------------------------------------------------------------------------------------------- |
| 色           | `src/styles/tokens.css` で shadcn のセマンティックトークン（`--background` など）に値を割り当てる |
| ユーティリティ | `src/index.css` の `@theme inline` でトークンを Tailwind に公開する（`bg-background` など）   |
| 書体         | 和文は Murecho、欧文は IBM Plex Sans を `main.tsx` で読み込む。等幅は OS の `ui-monospace` 系 |
| 角丸         | ボタン・入力 2px、カード 4px。ピルと円だけ `rounded-full`。例外はチャットの入力欄の `rounded-[1.25rem]`（テーマが `rounded-3xl` まで 4px に潰しているので値で指定する） |
| 動き         | `transition-*` の既定は 300ms + `--ease`。`transition-all` は使わない                         |

変更するときの注意:

- 色はトークン経由で指定し、コンポーネントに直書きしない。
- 文字色は地（`--background`）と面（`--card`）の上で 4.5:1 以上にする。`--primary` に白文字は
  コントラストが足りないので、`--primary-foreground` は暗い色にしている。
- トークンは `@theme` のない `tokens.css` の `@layer base` に置く。Tailwind v4 で `@theme` と同じ
  ファイルの素の `:root` が出力から落ちた事例があるため（4.2.2 では再現しない）。CSS を変えたら
  ビルドが通るだけで済ませず、`getComputedStyle` で実際に解決されることを確かめる。
- ダイアログに閉じるアニメーションを付けない。その間もボタンを押せるので、続けて押すと確定処理が
  2 回走る（E2E の `talk.spec.ts` で確かめている）。
- `<html class="dark">` は、shadcn のレジストリから足す部品の `dark:` バリアントを効かせるために
  残している（既存の部品には `dark:` はない）。

## チャット

履歴はサーバーが持ち、画面の状態は Zustand の `stores/chat-store.ts` が持つ。assistant-ui は
`useExternalStoreRuntime`（`features/talk/useChatRuntime.ts`）で描画と入力欄だけを受け持つ。
`setMessages` は渡さず、分岐も持たない。仕様の正は
[django_api/features/talk/README.md](../django_api/features/talk/README.md)。

| 機能 | 動作 |
| ---- | ---- |
| URL | `/talk` が新規チャット、`/talk/<id>` が既存のチャット。見つからなければ `/talk` へ移る。読み込みに失敗したら送信を止めて再読み込みの導線を出す。id は API のパスに入るので、UUID に使う文字だけを通す（react-router が `%2F` を `/` に戻すため、細工したリンクで別の API を呼ばれないように） |
| 新規チャット | Talk 設定と、その設定のシーン（任意。既定は「なし」）を選び、最初の送信でセッションを作る。どちらも作成後は変えられない。Talk 設定は前回の選択を覚える（`localStorage` の `talk-selected-setting`）が、シーンは覚えず、Talk 設定を選び直すと「なし」に戻る。シーンのない Talk 設定ではシーンの選択を出さない。選べる Talk 設定がなければ選択を止めて案内する。URL が変わっても画面は作り直さない（`threadKey` はセッションを切り替えたときだけ変える） |
| 逐次表示 | `POST`/`PATCH` に `Accept: text/event-stream, application/json` を付け、`lib/sse.ts` で読む。発話はすぐ出し、assistant の行は最初の `delta` で作る。`message`（保存の通知）を受けたら生成中を解くので、音声の合成中も次を送れる |
| メッセージの id | 行の key は生涯変わらない `localId`（`srv-<id>` か `local-<連番>`）。サーバー id に置き換えると行がリマウントするので、別のフィールドと `metadata.custom` に持つ |
| 失敗 | `error` イベント、HTTP エラー、接続できない場合は発話を取り消してサーバーの文言をバナーに出し、本文を入力欄へ戻す（編集なら編集欄を開き直す）。作ったばかりの空セッションは消す |
| 停止 | 読み取りを中断する。発話と途中の応答は残り、入力欄は変わらない。サーバーは切断を検知してから保存するので、`GET` を 500ms 間隔で最大 10 秒確認して揃える。その間は送信できない |
| 接続切れ | 終端イベントなしで切れた場合は停止と同じく同期する。保存が確認できなければ本文を入力欄へ戻す |
| 切り替え | 生成中に別のチャットへ移ると読み取りを中断する。サーバーは途中までを保存するので、裏で確認して一覧へ反映し、戻っていれば表示にも反映する |
| 削除されたチャット | 送信や編集が 404 になったら `GET` で確かめ、消えていれば `/talk` へ移って本文を入力欄へ戻す（編集対象のメッセージが消えた 404 ではチャットに留まる） |
| 続けられないチャット | Talk 設定が無効になった、またはシーンが使えなくなった（無効にした・Talk 設定から外した）チャットへの送信と編集は 400 になる。専用の表示はなく、ほかの失敗と同じくサーバーの文言をバナーに出して本文を戻す。Talk 設定へ移せなかった古いチャットは「（Talk 設定なし）」と表示する |
| 編集・再生成 | どちらも編集 API で対象以降を置き換える。再生成は履歴を失わないよう最後の応答にだけ出す |
| 50 件上限 | 達したら送信を止めて「新しいチャット」の導線を出す。競合で 400 が返ったらサーバーの文言を出して本文を戻す。編集は件数が増えないのでできる |
| 4000 字 | 超えたら送信を止める。`maxLength` は貼り付けを黙って切るので使わない |
| Markdown | `remark-gfm` と、改行をそのまま改行にする `remark-breaks`。生の HTML は描画しない。外部の画像は自動で読み込まず、リンクにする。リンクは別タブで開く |

変更するときの注意:

- `@assistant-ui/*` はバージョンを完全固定している。実験的な API を含むので、上げるときは
  `tests/features/talk/chat-runtime.test.tsx` と `e2e/talk.spec.ts` を流す。
- `stores/` と `features/talk/SessionNav.tsx` は初期チャンクに載るので assistant-ui に依存させない。
  送れなかったことは `SendResult` で返し、`MessageNotSentError` への変換は `useChatRuntime.ts` で行う。
- `ChatPage` は遅延読み込みなので、assistant-ui は他のページの初期チャンクに載らない。

## ディレクトリ構成

```
frontend/
├── src/
│   ├── App.tsx                  # ルーティング定義
│   ├── index.css                # Tailwind の読み込み・@theme・ベーススタイル
│   ├── styles/
│   │   └── tokens.css           # 色・寸法のトークン
│   ├── assets/                  # ブランド資産（渦マーク）
│   ├── components/
│   │   ├── ui/                  # shadcn/ui コンポーネント
│   │   ├── assistant-ui/        # assistant-ui のレジストリから取得した部品（markdown-text など）
│   │   ├── layout/              # AppLayout, Sidebar, nav-items
│   │   ├── audio/               # AudioPlayer, AudioDownload
│   │   ├── auth/                # ProtectedRoute
│   │   └── common/              # PageHeader, ConfirmDialog, LoadingButton, ErrorMessage
│   ├── features/
│   │   ├── home/                # ホーム画面
│   │   ├── login/               # ログイン画面
│   │   ├── tts/                 # テキスト読み上げ
│   │   ├── talk/                # チャット（React.lazy 遅延ロード）
│   │   │   ├── ChatPage.tsx              # URL とストアの同期、runtime の提供
│   │   │   ├── useChatRuntime.ts         # ストアを assistant-ui の runtime へつなぐ
│   │   │   ├── ChatThread.tsx            # メッセージ、アクション、入力欄、編集欄
│   │   │   ├── ChatHeader.tsx            # タイトル、Talk 設定とシーン、音声の一括操作
│   │   │   ├── ChatNotices.tsx           # 失敗、50 件上限、同期中の知らせ
│   │   │   ├── MessageAudio.tsx          # 応答の音声（合成中 / 失敗 / 再生・DL・削除）
│   │   │   ├── SessionNav.tsx            # サイドバーの一覧と新しいチャット
│   │   │   ├── SessionListItem.tsx       # タイトル / 日時 / サイズ / 削除
│   │   │   ├── SessionTitleEditor.tsx    # タイトルのインライン編集
│   │   │   ├── TalkSettingPicker.tsx     # Talk 設定とシーンの選択（新規時のみ）と作成後の表示
│   │   │   ├── AudioBundlePlay.tsx       # 一括再生（4 状態, iOS Safari 対応）
│   │   │   └── AudioBundleDownload.tsx   # 一括 DL（WAV を 1 秒無音入りで結合）
│   │   ├── media/               # メディア変換
│   │   └── pdf-edit/            # PDF編集（React.lazy 遅延ロード）
│   │       ├── PdfEditPage.tsx           # ページ本体
│   │       ├── components/               # アップローダ / サムネイル格子(DnD) /
│   │       │                             # ツールバー / トリミングダイアログ / DL ボタン
│   │       └── hooks/                    # usePdfDocument / useHighResPreview /
│   │                                     # useEditorKeybindings
│   ├── hooks/                   # 共通のフック（use-copy-to-clipboard）
│   ├── lib/
│   │   ├── api-client.ts        # ky インスタンス（Auth自動付与）
│   │   ├── api/                 # API 関数（auth, tts, talk, media, errors）
│   │   ├── sse.ts               # Server-Sent Events のパーサー
│   │   ├── audio/               # concat / bundleLoader（音声結合・取得）
│   │   ├── format/              # bytes ヘルパ
│   │   └── pdf/                 # pdf.js 読込/描画・pdf-lib 編集出力・
│   │                            # Worker 設定・出力ファイル名
│   ├── stores/                  # Zustand ストア（auth, tts, chat, pdf-edit）
│   │                            # chat は chat-store / chat-state / chat-turn / chat-messages に分割
│   └── types/                   # TypeScript 型定義（auth, media, pdf-edit, talk, tts）
├── tests/                       # Vitest ユニットテスト
├── e2e/                         # Playwright E2E テスト
├── Dockerfile                   # マルチステージビルド（node → nginx）
├── nginx.conf                   # SPA + API プロキシ設定
└── public/
    └── favicon.svg              # ファビコン
```

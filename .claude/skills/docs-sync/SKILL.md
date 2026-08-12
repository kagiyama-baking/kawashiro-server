---
name: docs-sync
description: コード変更に伴うドキュメント更新チェック。コード・設定・CI・環境変数・API・adminモデルを変更した後、git commitを実行する前に必ず使用する。変更ファイル一覧から更新すべきドキュメントを対応マップで特定し、実態との乖離を同一ブランチ内で解消する。
---

# ドキュメント同期チェック

コード変更をコミットする前に、ドキュメントが実態から乖離しないかを確認するワークフロー。

## 原則（単一ソース原則 / SSOT）

- 各事実は「正」となるファイル1つにのみ書く。他ファイルからは相対リンクで参照する
- 既存の記述を見つけてもコピーせず、リンクを張る
- ドキュメント更新は、対応するコード変更と同じブランチ（可能なら同じコミット）に含める
- 「正」の一覧は `.claude/CLAUDE.md` の「ドキュメントマップ」を参照

## 手順

1. `git diff --name-only` と `git diff --cached --name-only`（コミット済み分を見るなら
   `git diff --name-only origin/develop...HEAD`）で変更ファイルを列挙する
2. 下の対応マップで、変更パターンに合致する「確認先ドキュメント」を特定する
3. 確認先の該当節を開き、変更後のコード実態と突合する（値・表の行・コマンド・図・リンク）
4. 乖離があればドキュメントを更新し、同じコミットに含める
5. どのパターンにも該当しなければ「更新不要」と判断してよい（下の条件参照）

## 対応マップ（変更ファイル → 更新を確認するドキュメント）

| 変更ファイルパターン | 確認先 |
|---|---|
| `django_api/django_api/settings.py`（環境変数の追加・既定値変更） | `django_api/.env.sample` + ルート `README.md` 環境変数表 |
| `django_api/django_api/settings.py`（INSTALLED_APPS・スロットリング・上限値） | `.claude/CLAUDE.md` リポジトリ構造 + `django_api/README.md` 機能一覧表 + 該当機能 README |
| `django_api/*/urls.py`・views の追加・削除 | `django_api/README.md` 機能一覧表 + 該当機能 README の API 表 |
| `django_api/integrations/` 配下の新アプリ追加 | `.claude/CLAUDE.md` リポジトリ構造 + `django_api/README.md` 機能一覧表 |
| `django_api/integrations/llm/`・`langfuse/`（モデル・クライアント・config） | `django_api/integrations/llm/README.md`（3レイヤ表・admin 表・命名規約） |
| `django_api/features/talk/`（モデル・constants・views・services） | `django_api/features/talk/README.md`（TalkConfig 表・API 表・上限値） |
| `django_api/features/media/views.py`（`MAX_*` 等の制限値） | `django_api/features/media/README.md` 制限値表 |
| `django_api/features/hn_agent/` | `django_api/features/hn_agent/README.md` |
| `django_api/integrations/weather/` | `django_api/integrations/weather/README.md` |
| admin 設定モデルの migration（フィールド増減・seed 投入） | 該当 README + `docs/initial-setup.md` の投入手順 |
| `@shared_task` の追加・改名 | 該当機能 README + `docs/initial-setup.md`（PeriodicTask 登録名） |
| `management/commands/` の追加・変更 | 該当機能 README の運用節（開発ツールなら `docs/development.md`） |
| `docker-compose*.yml`（サービス・ポート・volumes・command） | ルート `README.md` サービス表・永続ディレクトリ + `docs/development.md` 起動パターン + `docs/deployment.md` |
| `*/Dockerfile`（ベースイメージ・ビルド引数） | ルート `README.md` 技術スタック + `docs/deployment.md`（sbv2 は `sbv2_api/README.md`） |
| `.github/workflows/**` | `docs/deployment.md` ワークフロー詳細・Secrets + `.claude/CLAUDE.md` CI 節 |
| `django_api/pyproject.toml`（pytest・ruff 設定・依存メジャー更新） | `.claude/CLAUDE.md` コマンド + `docs/development.md`（ruff は `.claude/skills/ruff-linter/SKILL.md` も） |
| `django_api/tests/` のディレクトリ追加 | `.claude/CLAUDE.md` テスト構成ツリー |
| `frontend/src/features/` の画面追加・削除、`App.tsx` のルート変更 | `frontend/README.md` 画面構成 + ルート `README.md` 機能紹介 |
| `frontend/package.json`（scripts・packageManager・主要依存） | `frontend/README.md` + `docs/development.md` |
| `frontend/nginx.conf` | `frontend/README.md`（media の上限に影響する場合は `django_api/features/media/README.md` も） |
| `sbv2_api/server.py`・`config.yml`・`Dockerfile` | `sbv2_api/README.md`（API・モデル配置・環境変数・GPU 切替） |
| `secrets/` の鍵ファイル追加・改名 | `docs/initial-setup.md`（MS Graph 節） |
| ドキュメントの新規追加・移動 | `.claude/CLAUDE.md` ドキュメントマップ + ルート `README.md` ドキュメントマップ + 本ファイルの対応マップ |

## ドキュメント更新不要と判断できる条件

以下**のみ**の変更はドキュメント更新不要:

- テストコード（`django_api/tests/`・`frontend/tests/`・`frontend/e2e/`・`sbv2_api/tests/`）のみの変更
- 外部仕様（API・設定・環境変数・制限値・コマンド）が変わらないリファクタリング
- `uv.lock` / `pnpm-lock.yaml` のみの更新
- コメント・docstring・型注釈のみの変更
- ドキュメント自体（`*.md`）の変更
- `.gitignore`・エディタ設定のみの変更

## 報告形式

チェック後、コミット前に以下いずれかを1行で報告する:

- `docs-sync: <ファイル> の <節> を更新（<理由>）`
- `docs-sync: 更新不要（<該当した不要条件>）`

# HackerNews Agent — HN 監視・分析エージェント

## 目的

Hacker News のフロントページを定期監視し、急上昇するスレッドを検出して **AI が自律的に調査・分析**するエージェントシステム。「なぜ急上昇しているか」「コミュニティ内で意見が割れているか」「新技術への辛口視点」「セキュリティインシデントの対応指針」を AI が判断して調査し、結果を Slack に通知します。

Orchestrator は LangGraph ReAct Agent として動作し、スレッドの性質に応じて 3 種類の特化ツールを使い分けます。

| ツール | 用途 | 典型的な呼び出しパターン |
|---|---|---|
| `detective_investigate` | 汎用調査（タイトル和訳、注目理由、背景、コメント要約） | 一般ニュース → 単独 |
| `devils_advocate_analyze` | 新技術・Show HN・アーキテクチャ議論への辛口視点（懸念点・過去事例・批判コメント） | 新技術発表 → `detective` と併用 |
| `security_responder_analyze` | 脆弱性・CVE・インシデント対応指針（影響範囲・回避策・公式パッチ） | セキュリティ話題 → 単独 |

## 全体アーキテクチャ

```mermaid
flowchart TB
    subgraph Trigger["トリガー"]
        Beat["Celery Beat（定期）"]
        API["POST /hn-agent/run-all/<br/>POST /hn-agent/watcher/run/<br/>POST /hn-agent/investigate/"]
    end

    subgraph Watcher["Watcher（tasks.py）"]
        Poll["poll_front_page<br/>・HN Algolia API で取得<br/>・HNThread / HNThreadSnapshot 更新<br/>・スコア / 速度閾値判定"]
    end

    subgraph Orch["Orchestrator（orchestrator.py）"]
        ReAct["LangGraph ReAct Agent<br/>・system/user prompt を Langfuse 解決<br/>・3 ツールから発火条件に応じて選択<br/>・最大 10 ステップで停止<br/>・is_investigated 一元管理"]
    end

    subgraph Tools["サブエージェント（agents/*.py）"]
        Det["Detective<br/>汎用調査 + Tavily 背景検索"]
        Devil["Devil's Advocate<br/>辛口・批判的視点抽出"]
        Sec["Security Responder<br/>CVE / 影響範囲 / パッチ整理<br/>（Tavily でセキュリティ情報補強）"]
    end

    subgraph Report["Reporter（reporter.py）"]
        Slack["Slack Block Kit で通知<br/>・🔍 Detective レポート<br/>・🛑 辛口な意見<br/>・🚨 セキュリティ詳細"]
    end

    Trigger --> Watcher
    Watcher -->|閾値超えスレッド毎| Orch
    Orch -->|tool call| Det
    Orch -->|tool call| Devil
    Orch -->|tool call| Sec
    Det -->|結果| Orch
    Devil -->|結果| Orch
    Sec -->|結果| Orch
    Orch --> Report
```

## admin 項目と外部サービスのつながり

HN Agent が使う admin 設定と、実際に叩く外部サービスの対応関係です。

```mermaid
flowchart LR
    subgraph Admin["Django admin"]
        HN["HackerNews Agent設定<br/>・閾値 / ポーリング / 取得件数<br/>・推論深度<br/>・8本のプロンプト参照FK"]
        Service["LLMサービス設定<br/>orchestrator / detective /<br/>devils_advocate / security_responder"]
        Provider["LLM設定<br/>model_alias + Virtual Key"]
        Ref["Langfuseプロンプト参照<br/>hn-agent-* 8種"]
    end

    subgraph External["外部サービス"]
        LiteLLM[("LiteLLM Proxy<br/>/v1/chat/completions")]
        Langfuse[("Langfuse<br/>get_prompt(name, label)")]
    end

    HN -->|8本| Ref
    HN -.->|service_name で参照| Service
    Service -->|provider_config| Provider

    Provider ==>|Virtual Key + model_alias| LiteLLM
    Ref ==>|名前とラベルで取得| Langfuse
```

## 各コンポーネント詳細

### Watcher（`tasks.py`: `poll_front_page`）

HN フロントページを定期ポーリングし、スナップショットを蓄積。

- **入力**: なし（Celery Beat または `POST /hn-agent/watcher/run/` による手動トリガー）
- **処理**
  1. HN Algolia API で `HNAgentConfig.front_page_limit` 件を取得（デフォルト 30）
  2. `HNThread` を `get_or_create`
  3. `HNThreadSnapshot` にスコア・コメント数を時系列記録
  4. 前回スナップショットとの差分から**スコア上昇速度**を計算
  5. `score_threshold` または `velocity_threshold` を超えたスレッドを検出
  6. `auto_investigate=True` の場合、Orchestrator を Celery タスクとして起動
- **出力**: 取得件数、新規スレッド数、トリガー数

### Orchestrator（`orchestrator.py`）

LangGraph の **ReAct Agent** を使い、LLM が「どのツールをどの順で呼ぶか」を自律判断。

- **入力**: 調査対象 `HNThread`
- **処理**
  1. `HNAgentConfig.objects.get_active_config()` で有効設定を取得（8 FK を先読み）
  2. `LLMClient(service_name="orchestrator")` 相当の `ChatOpenAI` を構築
  3. `resolve_prompt(config.orchestrator_system_prompt)` で system prompt 解決
  4. `resolve_prompt(config.orchestrator_user_prompt, hn_id=..., title=..., …)` で user prompt 解決
  5. `create_react_agent(llm, [detective_investigate, devils_advocate_analyze, security_responder_analyze])` で 3 ツール対応の ReAct Agent を構築
  6. 各ツールの docstring（発火条件を含む）を見て LLM がどのツールを何回呼ぶかを判断
  7. いずれかのエージェントが結果を返した場合のみ `HNThread.is_investigated = True` を一元的に更新
  8. Reporter に結果を渡して Slack 通知
- **ツール選択の判断基準（System Prompt）**
  1. セキュリティ話題（脆弱性/CVE/情報漏洩/ハッキング/0-day） → `security_responder_analyze` 単独
  2. 新技術・プロダクト発表（Show HN/アーキテクチャ論争） → `detective_investigate` + `devils_advocate_analyze`
  3. それ以外（一般ニュース・話題性） → `detective_investigate` 単独
- **特徴**
  - `@observe(name="hn-agent/orchestrator", as_type="agent")` で Langfuse 上に agent span
  - `_finalize_trace` で `decision_log`（実行ステップ一覧）をメタデータに記録
  - セキュリティ単独呼び出しでも無限ループしないよう、`is_investigated` の責務を Orchestrator に一元化

### Detective Agent（`agents/detective.py`）

スレッド急上昇の原因を汎用的に総合分析。

- **入力**: 調査対象 `HNThread`
- **処理**
  1. HN Algolia API でコメントを再帰取得（最大 50 件）
  2. Tavily API で投稿者・トピックの背景情報検索（設定なしの場合は skip）
  3. `resolve_prompt(config.detective_system_prompt)` / `config.detective_user_prompt` で system/user prompt 解決
  4. `LLMClient(service_name="detective").generate_text(...)` で分析
  5. LLM の応答を JSON パース（`title_ja` / `why_trending` / `comment_highlights` など）
- **出力**: 構造化分析結果（Slack 通知用）
- **特徴**
  - `@observe(name="hn-agent/detective", as_type="tool")` で Orchestrator の子スパンとして記録

### Devil's Advocate Agent（`agents/devils_advocate.py`）

新技術・Show HN・アーキテクチャ議論などに対して、HN 民の辛口・批判的視点を抽出。

- **入力**: 調査対象 `HNThread`
- **処理**
  1. HN コメントを取得（最大 50 件、Tavily は使わない）
  2. `resolve_prompt(config.devils_advocate_system_prompt)` / `config.devils_advocate_user_prompt` で prompt 解決
  3. `LLMClient(service_name="devils_advocate").generate_text(...)` で分析
  4. LLM の応答を JSON パース
- **出力**: 構造化分析結果
  - `concerns[]`: 懸念点・トレードオフ
  - `past_cases[]`: 過去の類似技術 + 教訓
  - `critical_comments[]`: 批判的コメント（著者・意訳・観点カテゴリ）
  - `summary`: 辛口視点での総括
- **特徴**
  - `@observe(name="hn-agent/devils-advocate", as_type="tool")` で Orchestrator の子スパン

### Security Responder Agent（`agents/security_responder.py`）

脆弱性・CVE・情報漏洩・ハッキングなどのスレッドで、エンジニアの対応方針を明確化。

- **入力**: 調査対象 `HNThread`
- **処理**
  1. HN コメントを取得
  2. Tavily API で CVE / advisory / patch / workaround を検索（クエリ例: `f"{title} CVE advisory patch workaround"`、設定なしの場合は skip）
  3. `resolve_prompt(config.security_responder_system_prompt)` / `config.security_responder_user_prompt` で prompt 解決
  4. `LLMClient(service_name="security_responder").generate_text(...)` で分析
  5. LLM の応答を JSON パース
- **出力**: 構造化分析結果
  - `cve_ids[]`: CVE ID（無ければ `[]`）
  - `affected[]`: 影響を受ける製品・バージョン
  - `workarounds[]`: パッチが適用できない場合の回避策
  - `official_patch`: `{available, version, url}` 形式のパッチ情報
  - `severity`: `critical` / `high` / `medium` / `low` / `unknown`
  - `summary`: 対応指針サマリ
- **特徴**
  - `@observe(name="hn-agent/security-responder", as_type="tool")` で Orchestrator の子スパン

### Reporter（`reporter.py`）

調査結果を Slack Block Kit でフォーマットして通知。エージェントごとに専用のブロック構造を持つ。

- `report_detective(result)`: 🔍 汎用調査レポート（タイトル和訳・注目理由・コメントピックアップ）
- `report_devils_advocate(result)`: 🛑 HN 民の辛口な意見（懸念点・過去事例・批判コメント）
- `report_security_responder(result)`: 🚨 セキュリティインシデント詳細（severity を色付き emoji で表示、CVE・影響範囲・回避策・公式パッチ）

**URL サニタイズ**: LLM が生成した `official_patch.url` や Tavily 検索結果の URL は、`_sanitize_url` によって `javascript:` 等の危険スキームと `|`/`<`/`>`/改行の mrkdwn 構造破壊文字を拒否してから Slack に送信します。

## データモデル

| モデル | 説明 |
|---|---|
| `HNThread` | HN スレッドの基本情報（`hn_id`, `title`, `url`, `author`, `is_investigated`） |
| `HNThreadSnapshot` | スコア・コメント数の時系列スナップショット（上昇速度の計算用） |
| `HNAgentConfig` | エージェント動作パラメータ + 使用プロンプト 8 本（`LangfusePromptRef` FK：Orchestrator / Detective / Devil's Advocate / Security Responder それぞれ system / user） |

※ `Memory Agent` / `ThreadEmbedding` / `Investigation` モデルは廃止されました（Langfuse トレースで代替）。

## 設定の管理

Django 管理画面から（表示順は「AI ツール設定」グループ）:

| 設定画面 | 管理内容 |
|---|---|
| **LLM 設定**（`LLMProviderConfig`） | モデルエイリアス + LiteLLM Virtual Key |
| **LLM サービス設定**（`LLMServiceConfig`） | `orchestrator` / `detective` / `devils_advocate` / `security_responder` の 4 サービスにプロバイダを割り当て |
| **Langfuse プロンプト参照**（`LangfusePromptRef`） | `hn-agent-orchestrator-system/-user`, `hn-agent-detective-system/-user`, `hn-agent-devils-advocate-system/-user`, `hn-agent-security-responder-system/-user` の 8 本 |
| **Slack 通知設定** | Webhook URL（暗号化保存） |
| **Tavily** | API キー（Web 検索、Detective・Security Responder で使用、任意） |
| **HackerNews Agent 設定**（`HNAgentConfig`） | 推論深度、スコア閾値、速度閾値、ポーリング間隔、フロントページ取得件数、プロンプト 8 本 |

> **Note:** `devils_advocate` / `security_responder` の `LLMServiceConfig` は、`detective` の設定が存在する状態で migration 0012 を適用すると、同じ `LLMProviderConfig` を共有する形で **`is_active=False` の雛形**として自動生成されます。管理画面から個別のプロバイダーへ切り替え可能です。

## API エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/hn-agent/run-all/` | Watcher + Orchestrator 一括実行 |
| `POST` | `/hn-agent/watcher/run/` | Watcher のみ手動実行 |
| `POST` | `/hn-agent/investigate/` | 指定 `hn_id` を Orchestrator 調査 |
| `GET` | `/hn-agent/threads/` | 監視中スレッド一覧 |

## ファイル構成

```
features/hn_agent/
├── models.py                 # HNThread / HNThreadSnapshot / HNAgentConfig
├── tasks.py                  # Celery タスク（poll_front_page, run_orchestrator, cleanup_old_snapshots）
├── orchestrator.py           # LangGraph ReAct Agent ベースの Orchestrator
├── reporter.py               # Slack Block Kit フォーマッター
├── views.py                  # DRF API ビュー
├── serializers.py            # DRF シリアライザ
├── urls.py                   # URL ルーティング
├── admin.py                  # Django 管理画面設定
├── agents/
│   ├── detective.py          # Detective Agent（汎用調査 + Tavily 背景検索）
│   ├── devils_advocate.py    # Devil's Advocate Agent（辛口・批判的視点抽出）
│   └── security_responder.py # Security Responder Agent（CVE / パッチ整理）
└── management/
    └── commands/
        ├── run_hn_watcher.py       # Watcher 手動実行
        └── run_hn_investigation.py # Orchestrator 手動実行
```

## LLMOps（Langfuse 統合）

### プロンプト管理

| Langfuse プロンプト名 | 用途 |
|---|---|
| `hn-agent-orchestrator` | Orchestrator の system プロンプト（3 ツールの発火条件を明記） |
| `hn-agent-orchestrator-user` | Orchestrator の user プロンプト（`{{hn_id}}`, `{{title}}`, `{{url}}`, `{{author}}`, `{{score_info}}`） |
| `hn-agent-detective` | Detective の system プロンプト（JSON スキーマ指定） |
| `hn-agent-detective-user` | Detective の user プロンプト（`{{title}}`, `{{url}}`, `{{author}}`, `{{score_info}}`, `{{background_section}}`, `{{comments_section}}`） |
| `hn-agent-devils-advocate` | Devil's Advocate の system プロンプト（concerns / past_cases / critical_comments / summary の JSON スキーマ指定） |
| `hn-agent-devils-advocate-user` | Devil's Advocate の user プロンプト（`{{title}}`, `{{url}}`, `{{author}}`, `{{score_info}}`, `{{comments_section}}`） |
| `hn-agent-security-responder` | Security Responder の system プロンプト（cve_ids / affected / workarounds / official_patch / severity / summary の JSON スキーマ指定） |
| `hn-agent-security-responder-user` | Security Responder の user プロンプト（`{{title}}`, `{{url}}`, `{{author}}`, `{{score_info}}`, `{{comments_section}}`, `{{search_section}}`） |

Langfuse 未登録でも `LangfusePromptRef.fallback_text` で動作します。初期データは以下 2 本の migration で自動投入されます:

- `integrations/langfuse/migrations/0002_seed_default_refs.py`: Orchestrator / Detective 用 4 種
- `integrations/langfuse/migrations/0003_seed_new_agent_refs.py`: Devil's Advocate / Security Responder 用 4 種、および Orchestrator の fallback_text を 3 ツール判断基準付きに更新

### トレーシング

- `langfuse.openai.OpenAI` drop-in wrapper により、全 LLM 呼び出しが自動でトレース・記録
- `@observe` デコレータで API エントリーポイント / Orchestrator / Detective に span 階層を構築
- Orchestrator の `_finalize_trace` で判断ログを `decision_log` としてメタデータ保存

### 環境変数

| 変数 | 説明 |
|---|---|
| `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` | Langfuse 認証 |
| `LANGFUSE_BASE_URL` | self-hosted 使用時のみ |
| `LANGFUSE_TRACING_ENVIRONMENT` | `dev` / `prd` |

## 依存する外部サービス

| サービス | 用途 | 必須 |
|---|---|---|
| LiteLLM Proxy | LLM 呼び出しの共通入口（プロバイダー非依存） | 必須 |
| HN Algolia API | スレッド・コメント取得 | 必須（無料） |
| PostgreSQL | スレッド・スナップショット保存 | 必須 |
| Redis | Celery ブローカー | 必須（定期実行時） |
| Tavily API | Web 検索（背景調査） | 任意（未設定時は skip） |
| Slack Webhook | 調査結果通知 | 任意（未設定時は skip） |
| Langfuse | LLM トレーシング・プロンプト管理 | 任意（未設定時は fallback_text で動作） |

# HN Agent — Hacker News 監視・分析エージェント

## 目的

Hacker News（HN）のフロントページを定期監視し、急上昇するスレッドを検出して**AIが自律的に調査・分析**するエージェントシステム。単なる要約ツールではなく、「なぜ急上昇しているか」「過去に同じ話題はあったか」「コミュニティ内で意見が割れているか」を自ら判断して調査し、結果をSlackに通知する。

## 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────────┐
│ Celery Beat（定期実行）or API（手動実行）                            │
└────────────────────┬────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Watcher（tasks.py: poll_front_page）                                │
│ ・HN Algolia APIでフロントページをポーリング                        │
│ ・スコア・コメント数のスナップショットを記録                        │
│ ・スコア閾値超え or 上昇速度閾値超えのスレッドを検出               │
└────────────────────┬────────────────────────────────────────────────┘
                     ▼ 閾値超えスレッド毎に起動
┌─────────────────────────────────────────────────────────────────────┐
│ Orchestrator（orchestrator.py）                                     │
│ ・OpenAI Function Callingループで自律的にAgentを呼び分ける          │
│ ・LLMが「どのAgentを使うべきか」を判断する                         │
│ ・最大10ステップで停止（無限ループ防止）                            │
│                                                                     │
│  ┌──────────────┐  ┌──────────────────┐                            │
│  │ Memory Agent │  │ Detective Agent  │                            │
│  │              │  │                  │                            │
│  │ pgvectorで   │  │ コメント分析     │                            │
│  │ 過去類似     │  │ + Tavily背景調査 │                            │
│  │ スレッド検索 │  │ + LLM総合分析    │                            │
│  └──────────────┘  └──────────────────┘                            │
└────────────────────┬────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Reporter（reporter.py）                                             │
│ ・調査結果をSlack Block Kit形式で通知                               │
└─────────────────────────────────────────────────────────────────────┘
```

## Orchestratorの判断フロー

OrchestratorはOpenAIの**Responses API**を利用し、LLM自身が「次にどのAgentを呼ぶべきか」を自律判断する。`reasoning`パラメータにより、LLMの判断理由もトレースに記録される。

```
[LLM] スレッド情報を受け取る
  │
  ├→ reasoning: 「過去に類似スレッドがないか確認すべき」
  ├→ function_call: memory_search   → Memory Agentを実行 → 結果をLLMに返す
  │
  ├→ reasoning: 「急上昇の原因を調査する」
  ├→ function_call: detective_investigate → Detective Agentを実行 → 結果をLLMに返す
  │
  └→ message（テキスト応答）        → 調査完了、最終サマリーを出力
```

最初の2ステップは`tool_choice="required"`で強制的にAgent呼び出しを行い、3ステップ目以降は`tool_choice="auto"`でLLMが結論を出せるようにしている。

## 各コンポーネント詳細

### Watcher（tasks.py）

HNフロントページを定期ポーリングし、データを蓄積する。

- **入力**: なし（Celery Beatまたは手動トリガー）
- **処理**:
  1. HN Algolia APIでフロントページ上位30件を取得
  2. `HNThread`にスレッド情報を保存（get_or_create）
  3. `HNThreadSnapshot`にスコア・コメント数を時系列記録
  4. 前回スナップショットとの差分からスコア上昇速度を計算
  5. 閾値超えスレッドに対してOrchestratorをCeleryタスクとして起動
- **出力**: 取得件数、新規スレッド数、トリガー数のサマリー

### Memory Agent（agents/memory.py）

pgvectorのcosine similarityで過去スレッドとの類似性を検索する。

- **入力**: 調査対象`HNThread`
- **処理**:
  1. スレッドのタイトル+URLからOpenAI Embedding APIでベクトルを生成
  2. `ThreadEmbedding`に保存（既存なら再利用）
  3. pgvectorのCosineDistanceで全`ThreadEmbedding`と照合
  4. 類似度閾値（デフォルト0.85）以上のスレッドを返す
- **出力**: 類似スレッドのリスト（hn_id、タイトル、類似度）
- **Investigationに保存**: agent_type="memory"

### Detective Agent（agents/detective.py）

スレッドが急上昇している理由を総合的に調査する。

- **入力**: 調査対象`HNThread`
- **処理**:
  1. HN Algolia APIでコメントを再帰取得（最大50件）
  2. Tavily APIで投稿者・トピックの背景情報を検索
  3. コメントテキスト + 背景情報をLLMに渡して分析
  4. 「なぜ急上昇しているか」の構造化レポートを生成
- **出力**: 分析テキスト、背景情報ソース、分析コメント数
- **Investigationに保存**: agent_type="detective"
- **副作用**: `HNThread.is_investigated = True`に更新

### Reporter（reporter.py）

調査結果をSlack Block Kit形式でフォーマットして通知する。

- **対応フォーマット**:
  - Detective Report: 分析結果 + コメントピックアップ + 参考情報リンク
  - Memory Report: 類似スレッドリスト + 類似度

## データモデル

| モデル | 説明 |
|--------|------|
| `HNThread` | HNスレッドの基本情報（hn_id, title, url, author, is_investigated） |
| `HNThreadSnapshot` | スコア・コメント数の時系列記録（上昇速度計算用） |
| `ThreadEmbedding` | pgvectorによるembeddingベクトル（次元数は設定で可変） |
| `Investigation` | エージェント調査結果（agent_type + JSON result） |
| `HNAgentConfig` | エージェント動作パラメータ（閾値、次元数、ポーリング間隔） |

## 設定の管理

全てDjango管理画面（`/admin/`）から設定する。

| 設定画面 | 管理内容 |
|----------|---------|
| **OpenAI API設定** | APIキー、チャットモデル、Embeddingモデル |
| **Tavily API設定** | APIキー（Web検索用） |
| **Slack通知設定** | Webhook URL |
| **HN Agent設定** | 推論深度、Embedding次元数、スコア閾値、速度閾値、類似度閾値、ポーリング間隔 |

## API エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| `POST` | `/hn-agent/run-all/` | Watcher + Orchestrator一括実行 |
| `POST` | `/hn-agent/watcher/run/` | Watcherのみ手動実行 |
| `POST` | `/hn-agent/investigate/` | 指定hn_idのスレッドをOrchestrator調査 |
| `GET` | `/hn-agent/threads/` | 監視中スレッド一覧 |
| `GET` | `/hn-agent/investigations/` | 調査結果一覧 |
| `GET` | `/hn-agent/investigations/<id>/` | 調査結果の詳細 |

## ファイル構成

```
features/hn_agent/
├── models.py          # HNThread, HNThreadSnapshot, ThreadEmbedding, Investigation, HNAgentConfig
├── tasks.py           # Celeryタスク（poll_front_page, run_orchestrator, cleanup_old_snapshots）
├── orchestrator.py    # Responses APIベースのOrchestrator
├── tools.py           # OpenAI Responses API用ツール定義
├── prompts.py         # Langfuseプロンプト取得ヘルパー
├── reporter.py        # Slack通知フォーマッター
├── views.py           # DRF APIビュー
├── serializers.py     # DRFシリアライザ
├── urls.py            # URLルーティング
├── admin.py           # Django管理画面設定
├── agents/
│   ├── memory.py      # Memory Agent（pgvector類似検索）
│   └── detective.py   # Detective Agent（背景調査 + LLM分析）
└── management/
    └── commands/
        ├── run_hn_watcher.py       # Watcher手動実行
        └── run_hn_investigation.py # Orchestrator手動実行
```

## LLMOps（Langfuse統合）

全LLM呼び出しはLangfuseでトレース・記録される。

- **OpenAI drop-in wrapper**: `langfuse.openai.OpenAI`で全Generation/Embeddingを自動トレース
- **@observe デコレータ**: APIエントリーポイント（`_run_all_impl`, `_investigate_impl`）とOrchestrator/Agentにスパン階層を構築
- **Responses API + reasoning**: Orchestratorの判断理由をreasoningサマリーとして記録（対応モデルのみ）
- **プロンプト管理**: `prompts.py`経由でLangfuse UIからプロンプトのバージョン管理・A/Bテストが可能

環境変数:
- `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_BASE_URL`: Langfuse接続設定
- `LANGFUSE_TRACING_ENVIRONMENT`: `dev`（開発）or `prd`（本番）

## 依存する外部サービス

| サービス | 用途 | 必須 |
|---------|------|------|
| OpenAI API | Responses API（Orchestrator）+ Chat Completions（分析）+ Embedding | 必須 |
| HN Algolia API | スレッド・コメント取得 | 必須（無料） |
| Tavily API | Web検索（背景調査） | 任意（未設定時はスキップ） |
| Slack Webhook | 調査結果通知 | 任意（未設定時はスキップ） |
| Langfuse | LLMトレーシング・プロンプト管理 | 任意（未設定時は無効） |
| PostgreSQL + pgvector | Embedding保存・類似検索 | 必須 |
| Redis | Celeryブローカー | 必須（定期実行時） |

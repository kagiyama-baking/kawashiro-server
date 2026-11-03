# Companion — キャラクター設定とスキル

Companion は、全体で 1 つのエージェント設定（共通のキャラクター設定）と、用途ごとの「スキル」（おはよう・おかえり・おやすみ など）を持つ Django アプリです。呼び出し時の発話からエージェントが合うスキルを選び、その手順に従ってセリフを返す設計で、いずれ Talk のプリセット（`TalkConfig`）を置き換えます。

> **現状:** 今あるのは設定のモデルと管理画面、エージェントと常設ツール（`agent.py`）、スキルの読み込み（`skills.py`）です。実行サービス・実行 API はまだありません。

- キャラクター設定とスキルの本文は DB に持たず、`LangfusePromptRef` 経由で Langfuse 上の text プロンプトを参照します（参照の仕組みは [../../integrations/llm/README.md](../../integrations/llm/README.md)）
- スキルの一覧（名前・説明・本文の参照）は admin で、設定のインラインとして管理します

## 構成

```
features/companion/
├── apps.py                    # CompanionAppConfig（label: companion。モデル名と重ならないよう AppConfig を付ける）
├── models.py                  # CompanionConfig / CompanionSkill
├── admin.py                   # 設定 + スキルのインライン + 有効化アクション
├── agent.py                   # COMPANION_AGENT と常設ツール（get_datetime / get_weather / get_today_events）
├── skills.py                  # スキル → 実行ごとの遅延 capability（build_skill_capabilities）・本文の解決・loaded_skill
├── exceptions.py              # CompanionError / PromptUnavailableError
└── migrations/0001_initial.py
```

音声合成の項目は `integrations/tts/models.py` の抽象モデル `AbstractTTSSettings` から継承します（テーブルは持たないので tts アプリに migration はありません）。

## CompanionConfig リファレンス

有効にできるのは 1 件だけです。管理画面（「AI ツール設定 → Companion → Companion 設定」）から登録します。

| フィールド | 型 / 既定値 | 意味 | 入力チェック |
|---|---|---|---|
| `name` | CharField(255) | 設定の識別名 | 一意 |
| `is_active` | Bool, `False` | 有効な設定 | 有効にして保存すると、ほかの設定は無効になる |
| `persona_prompt_ref` | FK → `LangfusePromptRef`（PROTECT） | 全スキルに共通のキャラクター設定（system プロンプト）の参照 | 必須。参照中の `LangfusePromptRef` は削除できない |
| `area_code` | CharField(10), `""` | 天気予報の予報区コード（例: `130010`）。空なら天気を扱わない | 空か 6 桁の半角数字（`^[0-9]{6}\Z`。全角数字・末尾の改行は通さない） |
| `rate_limit` | PositiveInteger, `10` | 1 ユーザーが 1 分間に実行できる回数の上限 | 1 以上 |
| `tts_*`（9 項目） | `AbstractTTSSettings` から継承 | 音声合成の設定。項目・既定値は [Talk の `TalkConfig` 表](../talk/README.md#talkconfig-リファレンス) の `tts_*` 行と同じ | 同左 |
| `created_at` / `updated_at` | DateTime（自動） | 作成・更新日時（admin では読み取りのみ） | — |

- `save()` は `full_clean()` を呼ぶため、上の入力チェックは admin 経由でもコード経由でも必ず走ります。ほかの設定の無効化と保存は 1 つのトランザクションで行います。
- `CompanionConfig.objects.get_active_config()` は有効な設定を `persona_prompt_ref` ごと 1 クエリで返し、有効な設定がなければ `CompanionConfig.DoesNotExist` を送出します。
- `get_tts_options()` は TTS の項目を `TTSClient.synthesize` のキーワード引数の辞書にまとめます。`tts_enabled=False` なら `None`、`tts_model` が空なら `model` は `None`（SBV2 側の既定モデル）です。

## CompanionSkill リファレンス

設定ごとに複数登録します（Companion 設定の変更画面の下にあるインライン）。並び順は名前順です。

| フィールド | 型 / 既定値 | 意味 | 入力チェック |
|---|---|---|---|
| `config` | FK → `CompanionConfig`（CASCADE, `related_name="skills"`） | 属する設定 | 設定を消すとスキルも消える |
| `name` | CharField(64) | スキル名（例: `good-morning`） | 英小文字・数字をハイフンでつないだ形（`^[a-z0-9]+(-[a-z0-9]+)*\Z`）。大文字・`_`・`:`・空白、先頭・末尾・連続のハイフンは不可。`instrumentation` は予約（下記）。同じ設定の中で一意 |
| `description` | CharField(1024) | どんな発話のときに使うスキルか。モデルが読んでスキルを選ぶための文なので、発話の例を含める | 必須、1024 字以内。admin では複数行の入力欄 |
| `prompt_ref` | FK → `LangfusePromptRef`（PROTECT） | スキルの手順（本文）の参照 | 必須。参照中の `LangfusePromptRef` は削除できない |
| `is_enabled` | Bool, `True` | 無効にしたスキルは使わない | — |

- 名前の規則は Agent Skills の命名規則（英小文字・数字・ハイフン、64 字以内）に合わせています。`:` を含められないので、PydanticAI の capability の id（`:` は使えない。予約の `deferred_capabilities` も `_` を含むので通らない）にそのまま使えます。
- **`instrumentation` は予約しています。** `integrations/llm/apps.py` の `Agent.instrument_all` により、どの実行にも PydanticAI の Instrumentation（id: `instrumentation`）が入るため、同じ id のスキルを渡すと id の衝突で実行そのものが失敗します（`tests/features/companion/test_models.py` で確認）。
- 説明を `TextField` ではなく `CharField` にしているのは、`full_clean()` で字数の上限を確かめるためです（`TextField` の `max_length` はフォームの入力欄にしか効きません）。
- `save()` は `full_clean()` を呼びます。同じ設定の中で同じ名前を 2 つ入れると、admin ではインラインのエラーになり何も保存されません。

## 管理画面

- 設定の節: 基本設定 / キャラクター / 天気 / 回数制限 / 音声（畳んで表示）/ メタ情報（畳んで表示）
- キャラクター設定とスキル本文の参照は、`LangfusePromptRef` を検索して選びます（識別名・Langfuse プロンプト名・説明が検索対象）
- 一覧のアクション「選択した設定を有効にする」で有効な設定を切り替えられます（1 件だけ選ぶ。2 件以上選ぶとエラーになり、何も変わりません）

## スキル

`skills.py` の `build_skill_capabilities(skills)` が、スキルを PydanticAI の on-demand capability（`Capability(id=<スキル名>, description=<説明>, defer_loading=True)`）にします。並びは渡した順のままです。capability は解決した本文を覚えるので、実行ごとに組み立てて渡します。

- **モデルが最初に見るのは一覧（カタログ）だけです。** system にスキル名と説明が `- good-morning: 朝のあいさつ（「おはよう」など）` の形で並び、組み込みの `load_capability` ツールが足されます。一覧の見出し・囲み（`<context id="capability:deferred_capabilities">`）・後ろの注記は PydanticAI の英語の定型文です。本文はまだ送りません。
- **モデルが `load_capability`（引数 `id` にスキル名）を呼ぶと、そのスキルの本文が以降のリクエストに入ります。** ツールの結果（読み込んだ旨の英語の定型文だけ）の直後の system（`<context id="capability:<スキル名>">` で囲んだもの）として届き、ユーザーの発話やツールの結果には混ざりません（送る形は `tests/integrations/llm/test_runtime.py` の `TestCapabilitiesContract` で固定）。読み込まなかったスキルの本文は送りません。
- **本文は読み込まれたときに Langfuse から取り、1 回の実行で 1 回だけ解決します。** 読み込んだ後はリクエストのたびに本文を送りますが、最初に解決した本文を使い続けます（実行の途中で本文は変わりません）。解決は呼び出し元のスレッドで行います。
- **本文が空ならエラーです。** Langfuse から取れないときはフォールバックテキストを使います。解決した本文が空（空白だけを含む）なら、`PromptUnavailableError`（`exceptions.py`。参照の識別名を `ref_name` に持つ）で実行ごと止めます。読み込めた体で続けたり、そのスキルを飛ばしたりはしません。
- **本文は変数のない text プロンプトです。** `{{...}}` は展開せず、そのまま届きます。日時・天気・予定のデータは本文に埋め込めないので、下の「ツール」を呼ぶよう本文に書きます（ツール名は表の名前のとおりに書く）。
- **使ったスキルは `loaded_skill(messages)` で実行の履歴から取ります。** 最初に読み込みに成功したスキル名を返し、どれも読み込まなければ `None` です。不明な名前・読み込み済みのスキルを読み込もうとすると、モデルに再試行を求めるだけで数えません。再試行は PydanticAI の既定で 1 回までなので、続けて 2 回失敗すると実行が失敗します（`LLMOutputError`）。

## ツール

エージェント（`agent.py` の `COMPANION_AGENT`）が常に持つツールです。どのスキルを使うときも呼べます。

> **ツール名・引数名・説明（docstring）・返す JSON のキーは、Langfuse に置くスキル本文との契約です。** 変えるときはスキル本文も直してください（名前・説明・引数・返す形は `tests/features/companion/test_agent.py` で固定しています）。

| ツール | 引数 | 返す JSON |
|---|---|---|
| `get_datetime` | なし | `date`（`YYYY-MM-DD`）・`time`（`HH:MM:SS`）・`day_of_week`（英語の曜日名）・`day_of_week_ja`（日本語の曜日名）・`holiday_name`（祝日でなければ `null`）。祝日を確認できなかったときは `holiday_name` を `null` にし、`holiday_lookup_failed: true` を足す |
| `get_weather` | `day`: `0`=今日（省略時）/ `1`=明日 / `2`=明後日 | 天気予報クライアントの結果そのまま（`area_name`・`weather`・`temp_max`・`temp_min`・`pop_00_06`〜`pop_18_24` など。項目は [weather の README のレスポンス](../../integrations/weather/README.md#レスポンス)） |
| `get_today_events` | なし | `date`（今日の `YYYY-MM-DD`）と `events`（開始時刻の順）。各予定は `subject`・`start` / `end`（`HH:MM`。終日の予定と、読めない時刻は `null`）・`is_all_day`・`location`（なければ `""`） |

- 地域（予報区コード）はモデルに選ばせません。有効な設定の `area_code` を実行ごとの依存（`CompanionDeps`）で渡し、空なら天気予報 API を呼ばずに error を返します。`day` が 0〜2 以外なら引数の検証で弾き、クライアントを呼ばずにモデルへ再試行を求めます。
- 「今日」と現在時刻は Django のタイムゾーン（`TIME_ZONE`）で決めます。予定の時刻は、Graph が返す日本時間（クライアントが `Prefer: outlook.timezone="Asia/Tokyo"` を送る）をそのまま `HH:MM` にします。予定の本文の抜粋・主催者・リンクはモデルに渡しません。
- **失敗しても実行は止めません。** 天気予報 API と Graph（設定なし・認証・通信・取得の失敗。msal のトークン取得の通信エラーを含む）の既知の失敗は warning ログを出し、`{"error": "<短い日本語>"}` をモデルに返して実行を続けます。祝日 API の失敗も warning ログを出しますが、error にはせず日付と時刻を返します（あいさつは時間帯で変わるため）。想定外の例外は error にせず、実行ごと失敗させます（不具合を隠さない）。
- ツールは async で、外部 API と Graph の設定の読み込み（ORM）は `sync_to_async` で呼び出し元のスレッドに戻して動かします（[LLM の README の §6](../../integrations/llm/README.md#6-llm-の呼び出し方)）。

## Langfuse プロンプトの命名

| 用途 | Langfuse プロンプト名 | 種類 |
|---|---|---|
| キャラクター設定（全スキル共通） | `companion-system` | text |
| スキルの本文 | `companion-skill-<スキル名>`（例: `companion-skill-good-morning`） | text（変数なし） |

- `LangfusePromptRef` の識別名も、Langfuse プロンプト名と同じ名前にします。
- どちらも **migration では作りません**（リポジトリは公開しているので、本文を git に置かない）。Langfuse のプロンプトと `LangfusePromptRef` は手で作ります。Chat 型のプロンプトは未対応です（`fallback_text` に落ちます）。
- **開発と本番は 1 つの Langfuse を共有しています。** 開発の参照はラベル `staging` を使い、確定した版にだけ `production` を付けます。

## 初期セットアップ

LLM サービス設定の有効化からプロンプト・参照・設定の登録までの順序は [../../../docs/initial-setup.md](../../../docs/initial-setup.md) の「Companion 設定」を参照してください。

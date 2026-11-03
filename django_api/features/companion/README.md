# Companion — キャラクター設定とスキル

Companion は、全体で 1 つのエージェント設定（共通のキャラクター設定）と、用途ごとの「スキル」（おはよう・おかえり・おやすみ など）を持つ Django アプリです。実行 API（`POST /companion/run/`）で受け取った発話からエージェントが合うスキルを選び、その手順に従ってセリフを返します（音声合成が有効なら音声も）。いずれ Talk のプリセット（`TalkConfig`）を置き換えます。

- キャラクター設定とスキルの本文は DB に持たず、`LangfusePromptRef` 経由で Langfuse 上の text プロンプトを参照します（参照の仕組みは [../../integrations/llm/README.md](../../integrations/llm/README.md)）
- スキルの一覧（名前・説明・本文の参照）は admin で、設定のインラインとして管理します

## 構成

```
features/companion/
├── apps.py                    # CompanionAppConfig（label: companion。モデル名と重ならないよう AppConfig を付ける）
├── models.py                  # CompanionConfig / CompanionSkill
├── admin.py                   # 設定 + スキルのインライン + 有効化アクション
├── agent.py                   # COMPANION_AGENT・常設ツール（get_datetime / get_weather / get_today_events）・応答の方針（response_policy）
├── skills.py                  # スキル → 実行ごとの遅延 capability（build_skill_capabilities）・指定したスキルの本文の節（skill_instructions）・本文の解決・loaded_skill
├── services.py                # run_companion（1 回の実行）→ CompanionReply
├── serializers.py             # 実行 API の入力（prompt / skill）と応答（text / skill / audio_data / audio_format）
├── views.py                   # CompanionRunView（POST /companion/run/）・例外と HTTP ステータスの対応
├── throttling.py              # CompanionRateThrottle（有効な設定の rate_limit で、ユーザーごとに数える）
├── urls.py                    # app_name = "companion"（run/）
├── exceptions.py              # CompanionError / PromptUnavailableError / CompanionNotConfiguredError / UnknownSkillError
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
| `rate_limit` | PositiveInteger, `10` | 1 ユーザーが 1 分間に実行できる回数の上限（数え方は下の「API」の「回数制限」） | 1 以上 |
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

`skills.py` の `build_skill_capabilities(skills)` が、スキルを PydanticAI の on-demand capability（`Capability(id=<スキル名>, description=<説明>, defer_loading=True)`）にします。並びは渡した順のままです。capability は解決した本文を覚えるので、実行ごとに組み立てて渡します。スキルを指定した実行では capability を使わず、`skill_instructions(skill)` で本文を実行の指示の末尾に足します（下の「実行の流れ」）。

- **モデルが最初に見るのは一覧（カタログ）だけです。** system にスキル名と説明が `- good-morning: 朝のあいさつ（「おはよう」など）` の形で並び、組み込みの `load_capability` ツールが足されます。一覧の見出し・囲み（`<context id="capability:deferred_capabilities">`）・後ろの注記は PydanticAI の英語の定型文です。本文はまだ送りません。
- **モデルが `load_capability`（引数 `id` にスキル名）を呼ぶと、そのスキルの本文が以降のリクエストに入ります。** ツールの結果（読み込んだ旨の英語の定型文だけ）の直後の system（`<context id="capability:<スキル名>">` で囲んだもの）として届き、ユーザーの発話やツールの結果には混ざりません（送る形は `tests/integrations/llm/test_runtime.py` の `TestCapabilitiesContract` で固定）。読み込まなかったスキルの本文は送りません。
- **本文は読み込まれたときに Langfuse から取り、1 回の実行で 1 回だけ解決します。** 読み込んだ後はリクエストのたびに本文を送りますが、最初に解決した本文を使い続けます（実行の途中で本文は変わりません）。解決は呼び出し元のスレッドで行います。
- **本文が空ならエラーです。** Langfuse から取れないときはフォールバックテキストを使います。解決した本文が空（空白だけを含む）なら、`PromptUnavailableError`（`exceptions.py`。参照の識別名を `ref_name` に持つ）で実行ごと止めます。読み込めた体で続けたり、そのスキルを飛ばしたりはしません。
- **本文は変数のない text プロンプトです。** `{{...}}` は展開せず、そのまま届きます。日時・天気・予定のデータは本文に埋め込めないので、下の「ツール」を呼ぶよう本文に書きます（ツール名は表の名前のとおりに書く）。
- **使ったスキルは `loaded_skill(messages)` で実行の履歴から取ります。** 最初に読み込みに成功したスキル名を返し、どれも読み込まなければ `None` です。不明な名前・読み込み済みのスキルを読み込もうとすると、モデルに再試行を求めるだけで数えません。`run_companion` では続けて 3 回まで再試行でき、それを超えて失敗すると実行が失敗します（`LLMOutputError`。下の「上限と再試行」）。

## ツール

エージェント（`agent.py` の `COMPANION_AGENT`）が常に持つツールです。どのスキルを使うときも呼べます。

> **ツール名・引数名・説明（docstring）・返す JSON のキーは、Langfuse に置くスキル本文との契約です。** 変えるときはスキル本文も直してください（名前・説明・引数・返す形は `tests/features/companion/test_agent.py` で固定しています）。

| ツール | 引数 | 返す JSON |
|---|---|---|
| `get_datetime` | なし | `date`（`YYYY-MM-DD`）・`time`（`HH:MM:SS`）・`day_of_week`（英語の曜日名）・`day_of_week_ja`（日本語の曜日名）・`holiday_name`（祝日でなければ `null`）。祝日を確認できなかったときは `holiday_name` を `null` にし、`holiday_lookup_failed: true` を足す |
| `get_weather` | `day`: `0`=今日（省略時）/ `1`=明日 / `2`=明後日 | 天気予報クライアントの結果そのまま（`area_name`・`weather`・`temp_max`・`temp_min`・`pop_00_06`〜`pop_18_24` など。項目は [weather の README のレスポンス](../../integrations/weather/README.md#レスポンス)） |
| `get_today_events` | なし | `date`（今日の `YYYY-MM-DD`）と `events`（開始時刻の順）。各予定は `subject`・`start` / `end`（今日の時刻は `HH:MM`、今日以外の日の時刻は `YYYY-MM-DD HH:MM`。終日の予定と、読めない時刻は `null`）・`is_all_day`・`location`（なければ `""`） |

- 地域（予報区コード）はモデルに選ばせません。有効な設定の `area_code` を実行ごとの依存（`CompanionDeps`）で渡し、空なら天気予報 API を呼ばずに error を返します。`day` が 0〜2 以外なら引数の検証で弾き、クライアントを呼ばずにモデルへ再試行を求めます。
- 「今日」と現在時刻は Django のタイムゾーン（`TIME_ZONE`）で決めます。予定の時刻は、Graph が返す日本時間（クライアントが `Prefer: outlook.timezone="Asia/Tokyo"` を送る）のまま書きます。今日の予定には前の日から続く予定・次の日まで続く予定も入るので、今日以外の日の時刻には日付を付けます（例: 前の日の 22:00 から今日の 01:00 までの予定は `start` が `2026-11-03 22:00`、`end` が `01:00`。今日の 23:00 から 24:00 までなら `end` は次の日の `00:00` なので日付付き）。予定の本文の抜粋・主催者・リンクはモデルに渡しません。
- **失敗しても実行は止めません。** 天気予報 API と Graph（設定なし・認証・通信・取得の失敗。msal のトークン取得の通信エラーを含む）の既知の失敗は warning ログを出し、`{"error": "<短い日本語>"}` をモデルに返して実行を続けます（モデルには、応答の方針でその情報に触れないよう指示しています）。祝日 API の失敗も warning ログを出しますが、error にはせず日付と時刻を返します（あいさつは時間帯で変わるため）。日付と時刻は 1 回だけ読み、祝日はその日付で確かめます（祝日の確認に失敗しても読み直さないので、日の境目でずれません）。想定外の例外は error にせず、実行ごと失敗させます（不具合を隠さない）。
- ツールは async で、外部 API と Graph の設定の読み込み（ORM）は `sync_to_async` で呼び出し元のスレッドに戻して動かします（[LLM の README の §6](../../integrations/llm/README.md#6-llm-の呼び出し方)）。

## 実行の流れ

`services.py` の `run_companion(prompt, skill=None)` が 1 回の実行です。発話（`prompt`）に答えるセリフを生成し、`CompanionReply`（`text`: 前後の空白を除いたセリフ / `skill`: 使ったスキルの名前か `None` / `audio`: `TTSResult` か `None`）を返します。

| 順 | 処理 | 止まるとき（送出する例外） |
|---|---|---|
| 1 | 有効な設定を読み、有効なスキルを名前順に読む（キャラクター設定・本文の参照ごと 2 クエリ） | 有効な設定がない（`CompanionNotConfiguredError`） |
| 2 | `skill` を指定したら、有効なスキルの中から探す | 登録がない・無効・ほかの設定のスキル（`UnknownSkillError`。名前を `skill_name` に持つ） |
| 3 | LLM の接続設定 `get_llm_settings("companion")` を読む | LLM サービス設定 `companion` がない・無効（`LLMConfigurationError`） |
| 4 | キャラクター設定の本文を解決する | 本文が空（`PromptUnavailableError`） |
| 5 | 実行の指示を組み立てる（下の「スキルの指定と自動選択」）。指定したスキルの本文はここで解決する | 指定したスキルの本文が空（`PromptUnavailableError`） |
| 6 | エージェントを 1 回実行する（下の「上限と再試行」） | タイムアウト（`LLMTimeoutError`。1 リクエストごとのタイムアウトか、実行全体の `RUN_TIMEOUT` を過ぎた）、上限の超過・接続や HTTP の失敗（`LLMClientError`）、ツールの失敗が続いた（`LLMOutputError`）、読み込んだスキルの本文が空（`PromptUnavailableError`） |
| 7 | 応答の前後の空白を除く | 空（`LLMOutputError`。音声合成はしない） |
| 8 | 使ったスキルを決める（指定したスキル、なければ最初に読み込みに成功したスキル、どちらもなければ `None`） | — |
| 9 | Langfuse のスパンに出力を記録する（下の「トレース（Langfuse）」） | 止まらない（warning ログだけ） |
| 10 | 音声合成が有効なら `TTSClient().synthesize(text, **config.get_tts_options())` で合成する | 音声合成の失敗（`TTSTimeoutError` / `TTSNetworkError` をそのまま） |

- 1〜5 で止まったときはモデルを呼びません。スキル名の確認（2）は、LLM の接続設定を読む前に行います。
- 出力トークンの上限（`max_tokens`）は付けません（Talk の単発生成と同じ）。

### スキルの指定と自動選択

| | 自動選択（`skill` なし） | スキルの指定（`skill` あり） |
|---|---|---|
| 実行の指示（最初の system） | キャラクター設定 → 応答の方針（有効なスキルがあれば読み込みの一文を含む） | キャラクター設定 → 応答の方針（読み込みの一文なし） → 見出し `# 今回の手順` とスキルの本文 |
| スキルの一覧と `load_capability` | 有効なスキルがあれば渡す（一覧は実行の指示の後ろの、別の system） | 渡さない |
| スキルの本文が届くとき | モデルが読み込んだ後のリクエストから（会話途中の system） | 最初のリクエストから |
| 読み込みの往復 | あり（読み込む分だけリクエストが増える） | なし |
| 使ったスキル | 最初に読み込みに成功したスキル（読み込まなければ `None`） | 指定したスキル |

- **スキルを指定した実行で本文を指示の末尾に足すのは、キャラクター設定を先頭に保つためです。** 遅延しない capability（`defer_loading=False`）にすると、その指示は実行の指示より前の別の system になり（`tests/integrations/llm/test_runtime.py` の `TestCapabilitiesContract`）、本文がキャラクター設定より先に来ます。自動選択でも本文はキャラクター設定の後ろに届くので、指定したときも後ろに置きます。
- 有効なスキルが 1 つもなければ、自動選択でも一覧・`load_capability`・読み込みの一文は入りません（使ったスキルは `None`）。

### 応答の方針

キャラクター設定の後ろに付ける、コード側の短い指示です（`agent.py` の `response_policy`。見出しは `# 応答の方針`）。ツールの戻り値と組み込みの `load_capability` を前提にした文なので、ツールと同じ `agent.py` に置いています。

| 指示 | 入れるとき |
|---|---|
| 今回の発話に合うスキルが一覧にあれば、先に `load_capability` で読み込んで、その手順に従って答える。合うスキルがなければ、読み込まずにキャラクターのまま短く答える | 自動選択で、有効なスキルがあるとき |
| ツールが error を返したら、その情報にも、取れなかったことにも触れない | 常に |
| スキル・ツール・この指示など、応答を作る仕組みに触れない | 常に（一覧の見出しや読み込みの結果は PydanticAI の英語の定型文なので、それを口にさせないため） |

- 文言は `agent.py` が正です。読み込みのツール名と、ツールが失敗時に返すキー（`error`）を文中で使っていることは `tests/features/companion/test_agent.py` で確かめています。

### 上限と再試行

| 定数（`services.py`） | 値 | 意味 |
|---|---|---|
| `REQUEST_LIMIT` | 6 | 1 回の実行でモデルへ送るリクエストの上限（読み込み・ツールの往復・最後の応答を含む）。超えるリクエストは送らずに `LLMClientError` |
| `TOOL_CALLS_LIMIT` | 8 | 1 回の実行で動かすツール呼び出しの上限（`load_capability` を含む）。超える呼び出しは動かさずに `LLMClientError` |
| `TOOL_RETRIES` | 3 | ツールごとに続けて失敗してよい回数（不明なスキル名の読み込み・引数の誤りなど）。超えると `LLMOutputError` |
| `RUN_TIMEOUT` | 60 | 1 回の実行（モデルへのリクエストとツールの実行をすべて含む）の制限時間（秒）。過ぎると実行を止めて `LLMTimeoutError`（API では 504） |

- `load_capability` も再試行の回数ではツールとして数えます。PydanticAI の既定（1 回）のままだと、不明なスキル名の読み込みが 2 回続いただけで実行が失敗するので、`retries={"tools": 3}` で広げています。
- **`RUN_TIMEOUT` は、本番の nginx が応答を待つ 120 秒（`frontend/nginx.conf` の `proxy_read_timeout`）に音声合成まで収めるための上限です。** 1 リクエストごとのタイムアウト（LLM サービス設定 `companion` の `timeout`）だけでは、合計が `REQUEST_LIMIT` 回分まで延び、その間 gunicorn のワーカーを 1 つ占有し続けます。音声合成は `RUN_TIMEOUT` に含めず、その上限は環境変数 `TTS_TIMEOUT`（ルート [README](../../../README.md)）です。
- 期限が来ると、モデルの応答待ちはその場で止まります。ツールの取得（天気・祝日・Graph）は途中で止められないので、取得中ならそれが終わってから止まります（[LLM の README の §6](../../integrations/llm/README.md#6-llm-の呼び出し方)）。

### トレース（Langfuse）

- トレース名は `companion/run` です。入力には発話と `skill` を、出力にはセリフと使ったスキル（`{"text": ..., "skill": ...}`）だけを記録します。配下にエージェントの実行（`invoke_agent companion`）、モデルへのリクエスト（generation）、ツール（`load_capability` を含む）が入ります。
- **音声は Langfuse に送りません。** 戻り値は音声のバイト列を含むので自動では記録させず（`capture_output=False`）、現在のスパンを更新して出力を記録します（`tests/integrations/llm/test_tracing.py` で確認）。
- 出力は音声合成の前に記録するので、音声合成に失敗してもセリフは残ります（スパンはエラーになります）。記録に失敗しても warning ログを出すだけで、実行は続けます。
- Langfuse のセッション（会話 ID）はサービス名の `companion` です（[LLM の README の §6](../../integrations/llm/README.md#6-llm-の呼び出し方)）。

## API

`POST /companion/run/`（`views.py` の `CompanionRunView`）が `run_companion` を 1 回実行します。Token 認証（`Authorization: Token <token>`）＋ `IsAuthenticated` が必要で、応答は JSON だけです。実行は同期で、セリフ（と音声）ができてから応答します。

### リクエスト

| 項目 | 型 | 説明 |
|---|---|---|
| `prompt` | 文字列（必須） | 発話（例: `おはよう`）。1〜1000 文字。空白だけの発話は空とみなして 400。前後の空白・改行も除かずにそのまま渡す（Talk の発話の入力と同じ） |
| `skill` | 文字列 / `null`（任意） | 使うスキルの名前。スキル名と同じ規則（英小文字・数字をハイフンでつないだ形、64 字以内）で、前後の空白は除く。省略か `null` ならエージェントが選ぶ（上の「スキルの指定と自動選択」） |

### レスポンス（200）

| 項目 | 型 | 説明 |
|---|---|---|
| `text` | 文字列 | セリフ（前後の空白を除いたもの） |
| `skill` | 文字列 / `null` | 使ったスキルの名前（上の「実行の流れ」の 8） |
| `audio_data` | 文字列 / `null` | Base64 でエンコードした音声。音声合成が無効なら `null` |
| `audio_format` | 文字列 / `null` | 音声の形式（設定の `tts_format`: `wav` / `mp3` / `ogg`）。音声合成が無効なら `null` |

- Talk の `/talk/synthesize/` とはセリフのキーが違います（`greeting_text` ではなく `text`）。

### エラー

本文は `{"error": "<メッセージ>"}` です。ただし、入力の不正は項目ごとのエラー（例: `{"prompt": ["この項目は空にできません。"]}`）、401・429 と JSON として読めない本文は DRF の `{"detail": "..."}` です。5xx のメッセージは決まった文で、例外の内容（接続先・設定名など）は返さずにログへ出します。

| ステータス | 原因（`run_companion` の例外） | `error` |
|---|---|---|
| 400 | 入力の不正 | （項目ごとのエラー） |
| 400 | 指定したスキルが登録されていないか、無効（`UnknownSkillError`） | `スキル「<名前>」は登録されていないか、無効です` |
| 401 | トークンがない・不正 | （`detail`） |
| 429 | 回数の上限を超えた（下の「回数制限」） | （`detail`。`Retry-After` ヘッダ付き） |
| 503 | 有効な設定がない（`CompanionNotConfiguredError`）、LLM サービス設定 `companion` がないか無効（`LLMConfigurationError`）、キャラクター設定かスキルの本文が空（`PromptUnavailableError`） | `Companion の設定に問題があります` |
| 504 | LLM のタイムアウト（`LLMTimeoutError`。実行全体の `RUN_TIMEOUT` の超過を含む） | `AI 生成サービスへのリクエストがタイムアウトしました` |
| 504 | 音声合成のタイムアウト（`TTSTimeoutError`） | `音声合成サービスへのリクエストがタイムアウトしました` |
| 502 | LLM の失敗（`LLMClientError`。上限の超過・接続や HTTP の失敗と、`LLMOutputError` の応答の不正・空の応答・ツールの失敗の連続を含む） | `AI 生成サービスでエラーが発生しました` |
| 502 | 音声合成の失敗（`TTSNetworkError`。接続の失敗・200 以外の応答） | `音声合成サービスでエラーが発生しました` |
| 500 | それ以外 | `セリフの生成中に問題が発生しました`（トレースバックはログへ） |

- `LLMTimeoutError` は `LLMClientError` のサブクラスです。`views.py` の `_KNOWN_ERRORS` を上から順に照合するので、タイムアウトは 502 ではなく 504 になります。
- 音声合成で失敗したときもセリフは返しません（Langfuse のスパンには残ります。上の「トレース（Langfuse）」）。

### 回数制限

- 上限は有効な設定の `rate_limit`（1 分あたり、既定 10 回）で、ユーザーごとに直近 1 分の回数を数えます（`throttling.py` の `CompanionRateThrottle`）。超えると 429 を返し、`Retry-After` に次の 1 回が通るまでの秒数を入れます。
- 上限は毎回 DB から読むので、admin で変えると次のリクエストから効きます。上限を下げた直後（直近 1 分の回数が新しい上限より多いとき）も `Retry-After` を付けます（DRF の既定では付かない）。
- **回数制限を通ったリクエストは、結果によらず 1 回と数えます。** 生成の失敗（5xx）も、入力の不正・不明なスキル（400）も数えます。数えないのは、429 で断ったリクエストと、有効な設定がないとき（503）だけです。
- 回数の記録先は Django のキャッシュ（Redis。ルート [README](../../../README.md) の `CACHE_REDIS_URL`）で、全ワーカーが共有します。Redis に届かないときと、同時に送ったときの挙動は Talk と同じです（[Talk の README](../talk/README.md) の「上限・レート制限」）。

### 使用例

```bash
# エージェントにスキルを選ばせる
curl -X POST http://localhost:8000/companion/run/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "おはよう"}'
# => {"text": "おはようございます。...", "skill": "good-morning", "audio_data": "UklGRi...", "audio_format": "wav"}

# スキルを指定する（自動化向け。読み込みの往復がない分、速い）。音声合成が有効なら音声をファイルに書き出す
curl -s -X POST http://localhost:8000/companion/run/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "おはよう", "skill": "good-morning"}' \
  | jq -r .audio_data | base64 -d > reply.wav
```

## Langfuse プロンプトの命名

| 用途 | Langfuse プロンプト名 | 種類 |
|---|---|---|
| キャラクター設定（全スキル共通） | `companion-system` | text |
| スキルの本文 | `companion-skill-<スキル名>`（例: `companion-skill-good-morning`） | text（変数なし） |

- `LangfusePromptRef` の識別名も、Langfuse プロンプト名と同じ名前にします。
- どちらも **migration では作りません**（リポジトリは公開しているので、本文を git に置かない）。Langfuse のプロンプトと `LangfusePromptRef` は手で作ります。Chat 型のプロンプトは未対応です（`fallback_text` に落ちます）。
- **開発と本番は 1 つの Langfuse を共有しています。** 開発の参照はラベル `staging` を使い、確定した版にだけ `production` を付けます。

## 初期セットアップ

LLM サービス設定の有効化からプロンプト・参照・設定の登録、API での動作確認までの順序は [../../../docs/initial-setup.md](../../../docs/initial-setup.md) の「Companion 設定」を参照してください。

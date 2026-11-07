# Talk — 会話生成・チャットセッション

LLM・天気・予定・日時・TTS を束ねて「ひとこと」を生成する単発 API（`/talk/synthesize/`）と、過去発話を引き継ぐマルチターンのチャット履歴 API（`/talk/sessions/` 系）を提供する Django アプリです。

- 単発生成: `TalkConfig`（プリセット）に紐づく Langfuse プロンプトを解決し、必要な外部データを埋め込んで LLM に投げ、任意で TTS 音声を返す
- チャットセッション: `ChatSession` / `ChatMessage` として PostgreSQL に永続化し、TTS 音声は `MEDIA_ROOT` 配下にファイル保存して認可付きで配信する
- プロンプト本文は DB に持たず、`LangfusePromptRef` 経由で Langfuse 上のプロンプトを参照する（詳細は [../../integrations/llm/README.md](../../integrations/llm/README.md)）

## アーキテクチャ

```
features/talk/
├── models.py            # TalkSetting（Talk 設定）/ ChatSession / ChatMessage / TalkConfig（会話生成設定。廃止予定）
├── serializers.py       # リクエスト・レスポンス定義（content 上限 4000 文字）
├── services.py          # TalkService: プレースホルダー検出・並列取得・LLM・TTS
├── llm_agents.py        # PydanticAI エージェント（チャット・タイトル・単発生成）と履歴の変換
├── chat_turn.py         # チャットの 1 ターンの実行: prepare_turn / commit_turn / ChatTurnRunner
├── views/               # ビューは責務ごとに分割（外部からは features.talk.views.X で参照）
│   ├── __init__.py      # 各ビューの再エクスポート（urls.py 側は変更不要）
│   ├── _common.py       # 例外→HTTP マッピング / SESSION_MAX_MESSAGES / 音声保存ヘルパ
│   ├── _sse.py          # ターンの応答（SSE / JSON の切替）: format_sse / respond_with_turn
│   ├── synthesize.py    # TalkSynthesizeView, TodayInfoView, ConfigsListView
│   ├── sessions.py      # ChatSessionListCreateView, ChatSessionDetailView, SessionPagination
│   ├── messages.py      # ChatSessionMessageView, ChatSessionMessageEditView（検証のみ）
│   └── audio.py         # ChatSessionMessageAudioView, ChatSessionAudioBulkDeleteView
├── signals.py           # post_delete で音声ファイルを物理削除（apps.ready() で登録）
├── permissions.py       # IsSessionOwner（session / session 経由オブジェクトの所有者判定）
├── throttling.py        # TalkConfigRateThrottle（/talk/synthesize/ のプリセットごとの回数制限）
├── admin.py             # Talk 設定 / ChatSession / ChatMessage / 会話生成設定（廃止予定）の管理画面
└── management/commands/cleanup_orphan_audio.py
```

`TalkService` は TTS・祝日・天気・Outlook の各クライアントをすべて遅延初期化（プロパティ経由）で保持します。祝日クライアント（holidays-jp API。インスタンス内キャッシュ）と日時情報の組み立て（`get_datetime_info`。`{{datetime}}` と `GET /talk/datetime/` が共用）は `integrations/holiday/` にあります。LLM は `llm_agents.py` の 3 エージェントを、チャットは `stream_text_sync`、タイトルと単発生成は `run_agent_sync` で実行し、接続設定は呼び出しごとに `get_llm_settings("talk")` で解決します（詳細は [../../integrations/llm/README.md](../../integrations/llm/README.md)）。本文のない応答（出力上限やフィルターで本文がなくなったものを含む）は再試行せず空文字として扱います。テストでは LLM を `TALK_CHAT_AGENT.override(model=...)` で差し替えます（`tests/features/talk/conftest.py` の `chat_llm` / `title_llm`）。

## Talk 設定（TalkSetting）リファレンス

チャットのシステムプロンプト・選べるシーン・音声をまとめた設定です。管理画面の「AI ツール設定 → Talk → Talk 設定」から登録し、**複数を有効にできます**（Companion 設定と違い、1 件に絞りません）。登録の手順は [../../../docs/initial-setup.md](../../../docs/initial-setup.md) の 5-4 を参照してください。

| フィールド | 型 / 既定値 | 説明 |
|---|---|---|
| `name` | CharField(255), unique | フロントの Talk で選ぶときに出る名前（自由記述） |
| `is_enabled` | Bool, `True` | 有効な設定だけを、フロントの Talk で選べて、続けて話せる |
| `system_prompt_ref` | FK → `LangfusePromptRef`（PROTECT） | チャットのシステムプロンプト（Langfuse の text プロンプト）の参照。必須。変数（`{{weather}}` など）は展開しない |
| `skills` | M2M → `AgentSkill`（`related_name="talk_settings"`） | この設定で選べるシーン（[Agent Skills](../../integrations/llm/README.md#agent-skillsagentskill) に登録したもの）。任意。無効にしたスキルは選べない |
| `tts_*`（9 項目） | `AbstractTTSSettings`（`integrations/tts/models.py`）を継承 | 項目と既定値は下の TalkConfig の表の `tts_*` 行と同じ。`get_tts_options()` は `tts_enabled=False` なら `None` |
| `created_at` / `updated_at` | DateTime | 作成・更新日時 |

- `save()` は `full_clean()` を呼びます（登録済みの名前で保存すると、admin では名前の欄のエラーになります）。並び順は名前順です。
- **シーンは、スキル名と同じ名前の Langfuse の text プロンプトの本文です**（スキルのラベルの版。フォールバックはありません）。ツールを使わないので、本文はツールを前提にせず、変数も書きません。
- チャットセッションは、作成時に Talk 設定（`setting`）とシーン（`skill`。なしなら空）を固定して持ちます（どちらも `on_delete=PROTECT`）。**チャットで使った Talk 設定とスキルは消せません。** 使わなくなったら無効にしてください。
- 旧プリセット名（`ChatSession.config_name`）は、Talk 設定より前のチャットのプリセット名です（移行の元。新しいチャットでは空。会話生成設定と一緒に削除する予定）。
- LLM の接続先は「AI設定 → サービス設定」の `Talk`（`talk`。会話生成設定と共通）です。

> **Note（既存のチャットの移行）:** migration `0018` は、Talk 設定のないチャットに使われているプリセットごとに、同じシステムプロンプトと音声の Talk 設定（有効・シーンなし）を作り、そのチャットを紐づけます（更新日時は変えないので、一覧の順は変わりません）。名前はプリセットの表示名（空白だけならプリセット名）で、表示名がほかのプリセットと重なるときは「表示名（プリセット名）」です。同じ名前の Talk 設定がすでにあり、システムプロンプトも同じなら、作らずにそれへ紐づけます（音声は違ってもよい）。システムプロンプトが違うか、作る名前どうしが重なるときは、何も変えずに `RuntimeError` で止まります（起動時の migrate が止まるので、重なる表示名か Talk 設定の名前を変えてから起動し直します）。プリセットが消えたチャットは紐づかず、続けられません（新しいチャットで話す）。旧プリセット名は変えません。
>
> 戻し方: `0018` の戻しは何もしません。`python manage.py migrate talk 0016` で Talk 設定の表と列ごと外れ、旧プリセット名で動く版のコードに戻せます（Talk 設定の行は消えます。`0017` 以降で作ったチャットは旧プリセット名が空なので、旧版では続けられません）。旧版のコードが `0018` の後に作ったチャット（Talk 設定がなく、旧プリセット名がある）は、`migrate talk 0017` → `migrate talk` で紐づけ直せます（前進は、もう紐づいたチャットには触れません）。

## TalkConfig リファレンス

> **廃止予定:** 会話生成設定は、チャットを Talk 設定へ、外部の自動化（`/talk/synthesize/`）を Companion へ移した後に削除します。

プリセットごとに複数登録可能（`morning` / `evening` / `welcome_home` …）。管理画面（`/admin/`）から登録します。

| フィールド | 型 / 既定値 | 説明 |
|---|---|---|
| `name` | CharField(50), unique | API 呼び出し時の識別子（例: `morning`） |
| `display_name` | CharField(100) | 管理画面での表示名 |
| `area_code` | CharField(10), `""` | 予報区コード。`^\d{6}$` の RegexValidator 付き（例: `130010`）。`{{weather}}` 使用時のみ必須 |
| `tts_enabled` | Bool, `False` | 音声合成の有効化。`False` ならテキストのみ返す |
| `tts_model` | CharField(100), `""` | TTS モデル名。空文字なら `None` として送られ SBV2 側の既定モデルを使う |
| `tts_style` | CharField(50), `"Neutral"` | 話者スタイル |
| `tts_style_weight` | Float, `1.0` | スタイル強度 |
| `tts_speed` | Float, `1.0` | 話速 |
| `tts_sdp_ratio` | Float, `0.2` | SDP 比率 |
| `tts_noise_scale` | Float, `0.6` | ノイズスケール |
| `tts_noise_scale_w` | Float, `0.8` | ノイズスケール W |
| `tts_format` | choices `wav` / `mp3` / `ogg`, 既定 `wav` | 出力音声フォーマット |
| `system_prompt_ref` | FK → `LangfusePromptRef` (PROTECT) | システムプロンプトの参照。必須 |
| `user_prompt_ref` | FK → `LangfusePromptRef` (PROTECT) | ユーザープロンプトテンプレートの参照。必須 |
| `synthesize_rate_limit` | PositiveInteger, `10`（1 以上） | `/talk/synthesize/` を 1 分間に呼べる回数。ユーザーとプリセットの組で数え、超えると 429（下の「上限・レート制限」）。この API にだけ効き、チャットには効かない |

- `save()` は `full_clean()` を呼ぶため、`area_code` の 6 桁チェックは admin 経由でもコード経由でも必ず走ります。
- `on_delete=PROTECT` のため、`TalkConfig` から参照されている `LangfusePromptRef` は削除できません。
- TTS 設定は `get_tts_options()` でまとめて辞書化され、`tts_enabled=False` のときは `None`（＝音声生成をスキップ）になります。
- `synthesize_rate_limit` は DB 側にも既定値（10）を持つので、イメージだけ前の版に戻しても（[../../../docs/deployment.md](../../../docs/deployment.md) のロールバック）、admin でプリセットを作れます。

> **Note (廃止フィールド):** かつて存在した `use_weather` / `use_events` / `use_datetime` は **migration `0014_remove_talkconfig_use_datetime_and_more` で削除済み**です。現在はプロンプト本文中の `{{placeholder}}` を自動検出する方式で、フラグによる有効・無効の切り替えはありません。

> **Note (プロンプト参照は手動):** `TalkConfig` 作成時に `LangfusePromptRef` が自動生成されることはありません（そのようなコードは存在しません）。migration `0012` は既存 config を移行するための一度きりのデータ移行です。新規プリセットでは **先に `LangfusePromptRef` を作成し、admin の autocomplete で選択**してください。

## プロンプトプレースホルダー

`TalkService.SUPPORTED_PLACEHOLDERS` は `{"weather", "events", "datetime"}` の 3 種です。プロンプト文字列に `{{weather}}` のような Mustache 風プレースホルダーを書くだけで、対応するデータが取得・展開されます。

**検出の仕組み**

1. `LangfusePromptRef` からプロンプトを解決し、変数集合を得る（Langfuse から取得できればその `variables`、失敗時は `fallback_text` を正規表現で走査）
2. 変数集合を `SUPPORTED_PLACEHOLDERS` と積集合して「本当に必要なキー」だけに絞る
3. `{{weather}}` が要求されているのに `area_code` が空なら、外部 API を呼ぶ前に `PlaceholderDataMissingError`（HTTP 400）
4. 必要なキーのみ `ThreadPoolExecutor(max_workers=min(len(tasks), 3))` で並列取得。`FIRST_EXCEPTION` で待ち、いずれかが失敗したら未完了の future をキャンセルして最初の例外を伝播
5. 取得結果を `json.dumps(..., ensure_ascii=False, indent=2)` で文字列化して埋め込む。要求されなかったキーは空文字で埋めるため、未使用の `{{...}}` がそのまま残ることはない

検出対象は API によって異なります。`/talk/synthesize/` は **system + user 両方**を走査し、チャット（`prepare_chat_prompt`）は **system プロンプトのみ**を走査します（ユーザー発話の中の `{{...}}` は展開されません）。

| プレースホルダー | データ源 | 埋め込まれる内容 | 前提 |
|---|---|---|---|
| `{{datetime}}` | サーバー時刻 + [holidays-jp API](https://holidays-jp.github.io/api/v1/date.json) | `date` / `time` / `day_of_week` / `day_of_week_ja` / `holiday_name`（祝日でなければ null） | 祝日 API への外部通信が必要（タイムアウト 10 秒） |
| `{{weather}}` | 気象庁（`WeatherClient.get_weather(area_code, 0)` ＝当日分） | 地域名・天気概況・最高/最低気温・時間帯別降水確率 | `area_code` 必須。未設定なら 400 |
| `{{events}}` | Outlook Calendar（`OutlookMSGraphClient.get_calendar_events`、本日分） | 当日のカレンダー予定一覧 | MS Graph 連携設定。不備時は 502 / 503 |

**プロンプトの用意**は手動作業です。Langfuse 上にプロンプトを登録し、Django 側に `LangfusePromptRef` を作成してから `TalkConfig` で選択します。命名は migration `0012` が使った `talk-<config_name>-system` / `talk-<config_name>-user` を慣例としています。Langfuse に到達できない場合は `LangfusePromptRef.fallback_text` が使われるため、最低限のフォールバック文面を入れておくと安全です。プロンプト管理の詳細は [../../integrations/llm/README.md](../../integrations/llm/README.md)、初期セットアップ手順は [../../../docs/initial-setup.md](../../../docs/initial-setup.md) を参照してください。

## API リファレンス

すべて Token 認証（`Authorization: Token <token>`）＋ `IsAuthenticated` が必要です。

**生成系**

| メソッド | パス | 用途 |
|---|---|---|
| `POST` | `/talk/synthesize/` | `config_name` のプリセットで会話を生成。任意の `user_prompt`（最大 4000 文字）を渡すと `user_prompt_ref` の代わりにその文字列を使う。プリセットの回数制限を超えると 429（下の「上限・レート制限」） |
| `GET` | `/talk/datetime/` | 本日の日付・時刻・曜日・祝日名を返す |
| `GET` | `/talk/configs/` | 登録済みプリセット一覧（`name` / `display_name` / `tts_enabled`） |

**チャット履歴セッション系**

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/talk/sessions/` | セッション一覧（`message_count` / `total_audio_bytes` 付き、更新日時の降順） |
| `POST` | `/talk/sessions/` | 新規作成。`config_name` は作成時に固定され、以降変更不可 |
| `GET` | `/talk/sessions/<uuid>/` | 詳細（messages 込み。音声は `audio_url` 経由） |
| `PATCH` | `/talk/sessions/<uuid>/` | タイトル更新 |
| `DELETE` | `/talk/sessions/<uuid>/` | セッション削除（メッセージと音声ファイルも消える） |
| `POST` | `/talk/sessions/<uuid>/messages/` | ユーザー発話を送信し assistant 応答を生成（201 でセッション詳細、または SSE で逐次。下記） |
| `PATCH` | `/talk/sessions/<uuid>/messages/<int>/` | user メッセージを編集して再送。対象以降は破棄して再生成（200 でセッション詳細、または SSE で逐次。assistant は編集不可で 400） |
| `GET` | `/talk/sessions/<uuid>/audio/<int>/` | 認可付き音声配信（`FileResponse`） |
| `DELETE` | `/talk/sessions/<uuid>/audio/<int>/` | 個別メッセージの音声だけ削除（本文は残す） |
| `DELETE` | `/talk/sessions/<uuid>/audio/` | セッション内の音声を一括削除（本文は残す） |

**送信・編集再送の応答（SSE / JSON）**

応答の形式は `Accept` で決まります。

| `Accept` | 応答 |
|---|---|
| `text/event-stream` を含む（例: `text/event-stream, application/json`） | 200 + SSE |
| それ以外（`application/json`、`*/*`、指定なし） | 同じ処理を最後まで実行し、送信は 201 / 編集は 200 + セッション詳細の JSON |
| `text/event-stream` のみ | 406（`JSONRenderer` のみの DRF が受け付けない） |

SSE を使うクライアントは `Accept: text/event-stream, application/json` を送ります。認証・スロットル・所有権・入力検証・プリセットの存在・件数上限・プロンプトの準備・LLM 設定の失敗は、SSE を要求しても通常の HTTP ステータスと JSON で返ります（ストリームは始まりません）。

各イベントは `event: <名前>` と `data: <JSON>` の 2 行で、UTF-8（日本語はエスケープしない）です。順序は `start` → `delta`（0 回以上）→ `message` → `audio` か `audio_error`（TTS 有効時のみ）→ `title`（生成時のみ）→ `done` です。

| イベント | data | 説明 |
|---|---|---|
| `start` | `{}` | 最初のイベント。LLM を呼ぶ前に流れ、ここで応答ヘッダが届く |
| `delta` | `{"text"}` | 本文の増分（約 50 ms ごとにまとまる）。連結すると保存される本文になる（保存できない NUL と孤立サロゲートは取り除く）。本文のない応答では流れない |
| `message` | `{"user", "assistant"}` | DB に保存した直後。中身はセッション詳細の `messages[]` と同じ形（`audio_url` はまだ `null`） |
| `audio` | `{"message_id", "audio_url", "audio_format", "audio_size_bytes"}` | 音声を保存した |
| `audio_error` | `{"message_id", "error"}` | 音声の合成か保存に失敗した。本文は残り、処理は続く |
| `title` | `{"title"}` | タイトルを生成した（手動で名前が付いたら流れない） |
| `done` | `{"title", "message_count", "total_audio_bytes", "updated_at"}` | 正常終了。セッション一覧の項目を更新できる |
| `error` | `{"status", "error"}` | 失敗して終了（これが最後のイベント）。`status` は JSON モードなら返す HTTP ステータス。写像は下のエラーマッピングと同じ |

**失敗と停止の挙動**

| 状況 | 動作 |
|---|---|
| LLM の失敗 | `error` を送って終わり、DB は変わらない（ユーザー発話も残らない）。編集でも元の履歴と音声が残る |
| 停止・切断（クライアントが接続を閉じる） | ユーザー発話と届いた分の応答を保存する（本文が空ならユーザー発話だけ）。編集なら対象以降を置き換える。音声とタイトルは実行しない |
| 音声の失敗 | 致命にしない。本文を残して `audio_error` を送り、続行する（JSON モードでは無視して 201 / 200） |
| 本文の保存後の切断 | 実行中の音声合成は完了して保存され、次の書き込みで切断に気づいて終わる（切断の直後の書き込みは成功することがあるので、タイトルの生成まで進むことがある） |
| セッションが途中で削除された | `error`（status 404）で終わり、何も保存しない |
| 同時送信 | コミット時に採番するので一意制約は壊れない。後から完了した方が末尾に付く（履歴の文脈はずれ得る） |

- 切断は次の書き込みで検知するので、クライアントが受け取った分より少し長い本文が保存されることがあります。`done` も `error` も来ないまま接続が切れたら、セッション詳細を取り直してください。
- 最初のトークンが届くまでは書き込みがないので、切断に気づきません。遅い応答を停止してすぐ次を送ると、停止した分はまだ保存されていないので次の応答の文脈に入らず、後から保存されると順序が入れ替わることがあります。
- 停止した応答に印は残りません（リロード後は普通の応答に見えます）。初回のターンを停止するとタイトルは空のままで、次のターンで生成します。タイトルの生成は会話の冒頭（履歴 2 件まで）に限るので、失敗したまま冒頭を過ぎたセッションは題が空のままです（手動で付けられます）。
- ヘッダは `Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache, no-transform`、`X-Accel-Buffering: no`（nginx のバッファを止める）です。ハートビートは送らないので、nginx の `proxy_read_timeout`（120 秒）がイベントの間隔の上限です。
- 本番の gunicorn は sync worker なので、1 ターン全体（LLM・音声・タイトル）が `--timeout` に収まる必要があります（ストリーミング中も延長されません）。超えるとワーカーが強制終了され、`done` も `error` もなく接続が切れます（切れる前に gunicorn が生のエラー応答を書くことがあります）。本文が届いていればそこまでを保存し、届く前なら LLM の失敗と同じく何も保存しません。ただし保存は SIGKILL までの短い猶予の中で行うので、確実ではありません。デプロイ時の停止で `graceful_timeout` を超えた場合は保存されません。

**上限・レート制限**

| 項目 | 値 | 備考 |
|---|---|---|
| throttle scope `talk_chat` | 20 リクエスト/分 | `ScopedRateThrottle`。メッセージ送信と編集再送に適用（`settings.py` の `DEFAULT_THROTTLE_RATES`） |
| `/talk/synthesize/` の回数 | プリセットごと（`TalkConfig.synthesize_rate_limit`、既定 10 回/分） | `TalkConfigRateThrottle`。ユーザーとプリセットの組で直近 1 分を数え、超えると 429 + `Retry-After`（次に通るまでの秒数）。失敗した生成も 1 回と数える。上限は毎回 DB から読むので、admin で変えると次のリクエストから効く。`config_name` を検証できない本文（400）とプリセットがないもの（404）は数えない（生成を始めてからの 400 / 404、たとえばプレースホルダーの設定不足や予報区コード不明は数える） |
| `SESSION_MAX_MESSAGES` | 50 | user + assistant の合計。到達後の送信は 400。編集再送は対象以降を置き換えるので確認しない。確認は事前検証で行うので、同時送信や編集で少し超えることがある |
| `content` 最大長 | 4000 文字 | 送信・編集どちらも同じ |
| `CHAT_MAX_OUTPUT_TOKENS` | 1024 | チャット応答の `max_tokens` |
| ページネーション | `default_limit=20` / `max_limit=100` | `LimitOffsetPagination`（セッション一覧のみ） |

スロットルの回数は Redis（Django のキャッシュ）に記録し、全ワーカーで共有します（接続先はルート [README.md](../../../README.md) の `CACHE_REDIS_URL`）。Redis に届かないと、スロットルの付いた API は 500 になります。記録の読み書きは原子的でないので、同時に送ると、同時に処理される数（ワーカー数）まで上限を超えて通ることがあります。

**認可**: セッション・メッセージ・音声のいずれも `user=request.user` でクエリセットを絞るため、他人の `session_id` / `msg_id` を指定しても 404 になります（`ChatMessage.id` はグローバル連番のため、編集・音声系では `session_id` と所有者の二重チェックを行っています）。

**エラーマッピング**（`views/_common.classify_synthesis_error`。HTTP の応答と SSE の `error` で共用）: プレースホルダー設定不足 → 400、予報区コード不明 → 404、外部 API/LLM/TTS/祝日のタイムアウト → 504、ネットワーク・パース・認証エラーと LLM の HTTP エラー（4xx / 5xx）や不正な応答 → 502、MS Graph 等の設定不備 → 503、それ以外 → 500。

## 内部挙動

**遅延コミット** — チャットの 1 ターンは LLM が完了または停止するまで DB に書きません（`chat_turn.py`）。LLM の間はトランザクションもロックも持たないので、生成中に他のリクエストを待たせません。LLM の失敗で元の履歴と音声が失われることもありません。

**タイトル自動生成** — `title` が空なら assistant 応答の後に `generate_session_title` が走ります（送信でも編集再送でも。停止した初回ターンの救済のため、メッセージ数は問いません）。履歴の先頭 4 件のみを使い、`max_tokens=60`、「日本語 1 行・20 文字以内」を指示、前後の引用符を除去し 50 文字で丸めます。失敗しても警告ログのみでチャット応答は返ります。更新は `title` が空の行だけに行うので、`PATCH /talk/sessions/<uuid>/` の手動の名前を上書きしません。

**sequence 採番** — LLM の完了後の短い `transaction.atomic` 内で `ChatSession` を `select_for_update()` してロックしてから、既存メッセージの最大 `sequence + 1` を user に、その次を assistant に割り当てます。`(session, sequence)` の `UniqueConstraint` と合わせて、同時 POST による採番の衝突を防いでいます。

**音声ファイルのライフサイクル** — 保存先は `talk_audio/<session_id>/<sequence>.<ext>`（`MEDIA_ROOT` 相対）。音声の合成とファイル書き込みは **DB の commit 後**に行い、ロールバック時にオーファンファイルが残らないようにしています。書き込みに失敗してもテキスト応答は保持され、音声フィールドだけ未設定になります。合成の間に行が削除されていたらファイルを残しません。`ChatMessage` の `post_delete` シグナルで、削除のコミット後にストレージ実体を物理削除するため、メッセージ削除・セッション削除（cascade）・編集再送での破棄いずれでもファイルは残らず、ロールバック時はファイルも残ります（テストで削除を確かめるときは `django_capture_on_commit_callbacks(execute=True)` を使います）。DB 行は残っているのに実体が消えている場合、音声 GET は 500 ではなく 404 を返します。本文のない応答は音声を合成しません。

**編集再送** — 対象より前の履歴だけを LLM に渡して応答を生成し、完了または停止した時点で、対象 `sequence` 以降のメッセージを（シグナルを確実に発火させるため）1 件ずつ削除して、同じ `sequence` で新しい user メッセージを作り直します。LLM の間に対象の行が消えていたら末尾に追加します。

**Langfuse Sessions 連携** — `synthesize` / `stream_chat_reply` / `generate_session_title` は `@observe` でトレースされ（それぞれ `talk/synthesize`、`talk/chat`、`talk/generate_session_title`）、チャット系では共有の `langfuse_session`（`integrations/langfuse/client.py`。`propagate_attributes` の with 文）がトレースと配下の観測に `session_id`（セッションの UUID）を付与します。Langfuse UI の Sessions で同一会話のトレースをまとめて追跡できます。付与に失敗しても警告ログのみで本処理は継続します。プレースホルダーの取得（`prepare_chat_prompt`）はストリームの前に行うので、`talk/prepare_chat` という別のトレースになります（入出力は記録しません）。`talk/chat` の出力は届いた本文で、停止した場合はそこまでの本文です。

## 運用

**孤児音声レコードの整理** — ボリューム喪失などで DB 上の `audio_file` パスだけが残った場合、次のコマンドで `audio_file` / `audio_format` / `audio_size_bytes` をクリアできます。

```bash
# 検出のみ（DB は更新しない）
docker compose exec django-api python manage.py cleanup_orphan_audio --dry-run

# 実際にクリア
docker compose exec django-api python manage.py cleanup_orphan_audio
```

**保存先** — `MEDIA_ROOT` はコンテナ内 `/django_api/media`（`BASE_DIR / "media"`）で、ホストの `/opt/app/django-api/media` をバインドマウントしています。音声はここに実ファイルとして蓄積されるため、`GET /talk/sessions/` が返す `total_audio_bytes` や上記コマンドで定期的に状況を確認してください。不要な音声は音声一括削除 API（本文は保持）で回収できます。

## 使用例

```bash
# 単発生成（TTS 有効なプリセットなら audio_data に Base64 の音声が入る）
curl -X POST http://localhost:8000/talk/synthesize/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"config_name": "morning"}'
# => {"greeting_text": "おはようございます。...", "audio_data": "UklGRi...", "audio_format": "wav"}
```

```bash
# 1) セッションを作成（プリセットは morning に固定される）
curl -X POST http://localhost:8000/talk/sessions/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"config_name": "morning"}'
# => {"id": "3f0c...", "title": "", "config_name": "morning", "messages": [], ...}

# 2) 発話を送信して assistant 応答を生成（返り値はセッション詳細）
curl -X POST http://localhost:8000/talk/sessions/3f0c.../messages/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "おはよう"}'
# => messages[1] が assistant。audio_url に音声取得用 URL が入る

# 2') SSE で受け取る場合（-N で curl のバッファを止める）
curl -N -X POST http://localhost:8000/talk/sessions/3f0c.../messages/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream, application/json" \
  -d '{"content": "おはよう"}'
# => event: start / event: delta ... / event: message / event: audio / event: done

# 3) 音声ファイルを取得（streaming）
curl http://localhost:8000/talk/sessions/3f0c.../audio/42/ \
  -H "Authorization: Token YOUR_TOKEN" \
  --output reply.wav
```

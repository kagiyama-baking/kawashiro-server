# Talk — 会話生成・チャットセッション

LLM・天気・予定・日時・TTS を束ねて「ひとこと」を生成する単発 API（`/talk/synthesize/`）と、過去発話を引き継ぐマルチターンのチャット履歴 API（`/talk/sessions/` 系）を提供する Django アプリです。

- 単発生成: `TalkConfig`（プリセット）に紐づく Langfuse プロンプトを解決し、必要な外部データを埋め込んで LLM に投げ、任意で TTS 音声を返す
- チャットセッション: `ChatSession` / `ChatMessage` として PostgreSQL に永続化し、TTS 音声は `MEDIA_ROOT` 配下にファイル保存して認可付きで配信する
- プロンプト本文は DB に持たず、`LangfusePromptRef` 経由で Langfuse 上のプロンプトを参照する（詳細は [../../integrations/llm/README.md](../../integrations/llm/README.md)）

## アーキテクチャ

```
features/talk/
├── models.py            # TalkConfig / ChatSession / ChatMessage
├── serializers.py       # リクエスト・レスポンス定義（content 上限 4000 文字）
├── services.py          # TalkService: プレースホルダー検出・並列取得・LLM・TTS
├── views/               # ビューは責務ごとに 5 分割（外部からは features.talk.views.X で参照）
│   ├── __init__.py      # 各ビューの再エクスポート（urls.py 側は変更不要）
│   ├── _common.py       # 例外→HTTP マッピング / SESSION_MAX_MESSAGES / 音声保存ヘルパ
│   ├── synthesize.py    # TalkSynthesizeView, TodayInfoView, ConfigsListView
│   ├── sessions.py      # ChatSessionListCreateView, ChatSessionDetailView, SessionPagination
│   ├── messages.py      # ChatSessionMessageView, ChatSessionMessageEditView
│   └── audio.py         # ChatSessionMessageAudioView, ChatSessionAudioBulkDeleteView
├── signals.py           # post_delete で音声ファイルを物理削除（apps.ready() で登録）
├── permissions.py       # IsSessionOwner（session / session 経由オブジェクトの所有者判定）
├── holiday_client.py    # holidays-jp API クライアント（インスタンス内キャッシュ）
├── constants.py         # DAY_OF_WEEK_JA（曜日の日本語マッピング）
├── admin.py             # TalkConfig / ChatSession / ChatMessage の管理画面
└── management/commands/cleanup_orphan_audio.py
```

`TalkService` は LLM・TTS・祝日・天気・Outlook の各クライアントをすべて遅延初期化（プロパティ経由）で保持します。LLM 設定は `LLMClient(service_name="talk")` で talk 用の設定が選択されます。テストで差し替える際は `features.talk.views.messages.TalkService` のように具体モジュールのパスを patch してください。

## TalkConfig リファレンス

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

- `save()` は `full_clean()` を呼ぶため、`area_code` の 6 桁チェックは admin 経由でもコード経由でも必ず走ります。
- `on_delete=PROTECT` のため、`TalkConfig` から参照されている `LangfusePromptRef` は削除できません。
- TTS 設定は `get_tts_options()` でまとめて辞書化され、`tts_enabled=False` のときは `None`（＝音声生成をスキップ）になります。

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

検出対象は API によって異なります。`/talk/synthesize/` は **system + user 両方**を走査し、チャット（`synthesize_chat`）は **system プロンプトのみ**を走査します（ユーザー発話の中の `{{...}}` は展開されません）。

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
| `POST` | `/talk/synthesize/` | `config_name` のプリセットで会話を生成。任意の `user_prompt`（最大 4000 文字）を渡すと `user_prompt_ref` の代わりにその文字列を使う |
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
| `POST` | `/talk/sessions/<uuid>/messages/` | ユーザー発話を送信し assistant 応答を生成（201 でセッション詳細を返す） |
| `PATCH` | `/talk/sessions/<uuid>/messages/<int>/` | user メッセージを編集して再送。対象以降は破棄して再生成（assistant は編集不可で 400） |
| `GET` | `/talk/sessions/<uuid>/audio/<int>/` | 認可付き音声配信（`FileResponse`） |
| `DELETE` | `/talk/sessions/<uuid>/audio/<int>/` | 個別メッセージの音声だけ削除（本文は残す） |
| `DELETE` | `/talk/sessions/<uuid>/audio/` | セッション内の音声を一括削除（本文は残す） |

**上限・レート制限**

| 項目 | 値 | 備考 |
|---|---|---|
| throttle scope `talk_chat` | 20 リクエスト/分 | `ScopedRateThrottle`。メッセージ送信と編集再送に適用（`settings.py` の `DEFAULT_THROTTLE_RATES`） |
| `SESSION_MAX_MESSAGES` | 50 | user + assistant の合計。到達後の送信は 400。編集再送は対象以降を削除するため件数は増えない |
| `content` 最大長 | 4000 文字 | 送信・編集どちらも同じ |
| `CHAT_MAX_OUTPUT_TOKENS` | 1024 | チャット応答の `max_tokens` |
| ページネーション | `default_limit=20` / `max_limit=100` | `LimitOffsetPagination`（セッション一覧のみ） |

**認可**: セッション・メッセージ・音声のいずれも `user=request.user` でクエリセットを絞るため、他人の `session_id` / `msg_id` を指定しても 404 になります（`ChatMessage.id` はグローバル連番のため、編集・音声系では `session_id` と所有者の二重チェックを行っています）。

**エラーマッピング**（`views/_common.handle_synthesis_error`）: プレースホルダー設定不足 → 400、予報区コード不明 → 404、外部 API/LLM/TTS/祝日のタイムアウト → 504、ネットワーク・パース・認証エラー → 502、MS Graph 等の設定不備 → 503、それ以外 → 500。

## 内部挙動

**タイトル自動生成** — 初回の assistant 応答後（`title` が空かつメッセージ数が 2）に `generate_session_title` が走ります。履歴の先頭 4 件のみを使い、`max_tokens=60`、「日本語 1 行・20 文字以内」を指示、前後の引用符を除去し 50 文字で丸めます。失敗しても警告ログのみでチャット応答は返ります。`PATCH /talk/sessions/<uuid>/` で手動上書きも可能です。

**sequence 採番** — `transaction.atomic` 内で `ChatSession` を `select_for_update()` してロックしてから、既存メッセージの最大 `sequence + 1` を user に、その次を assistant に割り当てます。`(session, sequence)` の `UniqueConstraint` と合わせて、同時 POST による採番の衝突と 50 件上限のすり抜けを防いでいます。

**音声ファイルのライフサイクル** — 保存先は `talk_audio/<session_id>/<sequence>.<ext>`（`MEDIA_ROOT` 相対）。ファイル書き込みは **DB の commit 後**に行い、ロールバック時にオーファンファイルが残らないようにしています。書き込みに失敗してもテキスト応答は保持され、音声フィールドだけ未設定になります。`ChatMessage` の `post_delete` シグナルでストレージ実体を物理削除するため、メッセージ削除・セッション削除（cascade）・編集再送での破棄いずれでもファイルは残りません。DB 行は残っているのに実体が消えている場合、音声 GET は 500 ではなく 404 を返します。

**編集再送** — 対象 `sequence` 以降のメッセージを（シグナルを確実に発火させるため）1 件ずつ削除してから、同じ `sequence` で新しい user メッセージを作り直し、対象より前の履歴だけを LLM に渡して応答を再生成します。

**Langfuse Sessions 連携** — `synthesize` / `synthesize_chat` / `generate_session_title` は `@observe` でトレースされ（それぞれ `talk/synthesize`、`talk/chat`、`talk/generate_session_title`）、チャット系では `_set_langfuse_session` がトレースに `session_id`（セッションの UUID）を付与します。Langfuse UI の Sessions で同一会話のトレースをまとめて追跡できます。付与に失敗しても警告ログのみで本処理は継続します。

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

# 3) 音声ファイルを取得（streaming）
curl http://localhost:8000/talk/sessions/3f0c.../audio/42/ \
  -H "Authorization: Token YOUR_TOKEN" \
  --output reply.wav
```

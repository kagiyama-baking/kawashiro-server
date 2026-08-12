# 初期セットアップガイド

新規環境を立ち上げた直後に一度だけ行う、**スーパーユーザー作成 → 管理画面での設定投入 → 定期タスク登録**の手順です。設定どうしに外部キー依存があるため、**本ページの順序どおりに投入してください**。

## 1. 前提

- コンテナが起動済みであること（[../README.md](../README.md) / [./development.md](./development.md) を参照）
- マイグレーションは `django-api` コンテナの起動コマンドに含まれるため、手動実行は不要です（`docker-compose.yml` の `command` で `migrate` → `collectstatic` → `runserver` の順に実行）
- **`django_api/.env` に `ENCRYPTION_KEY` が設定されていること**

`ENCRYPTION_KEY` は DB に保存する機密情報（LiteLLM Virtual Key、MS Graph 秘密鍵、Slack Webhook URL、Tavily API キー）の暗号化に使われます。**32 文字未満または未設定の場合、これらの項目を保存・読み出しした時点で `ValueError` になります**（`django_api/core/encryption.py`）。

```bash
openssl rand -base64 32   # 生成例
```

> **Warning:** `ENCRYPTION_KEY` を後から変更すると、暗号化済みの既存レコードは復号できなくなります。値は初回に決めて固定してください。

## 2. スーパーユーザー作成

```bash
docker compose exec django-api python manage.py createsuperuser
```

ユーザーモデルは `USERNAME_FIELD = "email"` のため、ユーザー名ではなく**メールアドレス**を入力します（`django_api/core/models.py`）。

作成後、`http://localhost:8000/admin/` にログインできることを確認してください。

## 3. 管理画面の構成

管理画面のアプリ表示順は `django_api/core/apps.py` の `ADMIN_APP_ORDER` で 3 グループに整列されています。

| グループ | 表示されるアプリ | 役割 |
|---|---|---|
| システム設定 | Core / 認証と認可 / 認証トークン | ユーザー、グループ、API トークンの管理 |
| 外部サービス設定 | Microsoft 365 / Slack / Tavily / Celery | 外部 API の資格情報と定期タスクのスケジュール |
| AI ツール設定 | LLM 設定 / Langfuse / HackerNews Agent / Talk Generator | LLM の割り当て、プロンプト参照、各機能の設定 |

「Celery」は `django-celery-beat` の表示名を変更したもので、定期タスク・インターバル・Cron スケジュール・時刻指定を扱います（太陽イベントは未使用のため非表示）。

## 4. AI 基盤の設定

### 4-1. LLM 設定（`LLMProviderConfig`）

「AI ツール設定 → LLM 設定 → LLM 設定」から作成します。モデルエイリアスと認証キーの組で、複数の LLM サービス設定から共有されます。

| 項目 | 説明 |
|---|---|
| 設定名 | 一意な識別名（例: `Kimi K2.5 本番`） |
| モデルエイリアス | LiteLLM Proxy の `model_name`（例: `bedrock/moonshotai.kimi-k2.5`） |
| Virtual Key | LiteLLM Virtual Key（暗号化保存）。**空のままにすると環境変数 `LITELLM_MASTER_KEY` が使われます** |

一覧の「Virtual Key」列で設定済みかどうかを確認できます。入力欄はパスワード形式で、保存済みの値は再表示されません（変更時のみ入力）。

### 4-2. LLM サービス設定（`LLMServiceConfig`）

どのサービスがどの LLM 設定を使うかを割り当てます。サービス名は 5 種で、それぞれ 1 レコードのみ登録できます。

| サービス名 | 用途 |
|---|---|
| HN Agent Orchestrator | HN Agent の司令塔 |
| HN Agent Detective | スレッドの分析 |
| HN Agent Devil's Advocate | 反論・批判的検証 |
| HN Agent Security Responder | セキュリティ観点の応答 |
| Talk Generator | 会話生成（`/talk/`） |

`LLM 設定` は必須の外部キー（`on_delete=PROTECT`）なので、**手順 4-1 を先に済ませてください**。`タイムアウト（秒）` の既定は 60、`有効` の既定は ON です。

> **Note:** `devils_advocate` / `security_responder` の 2 件は、マイグレーション `integrations/llm/migrations/0012_add_new_agent_service_choices.py` により、**既存の `detective` 設定を雛形として `is_active=False` で自動複製されます**（`detective` が存在する場合のみ）。新規環境で `detective` を未作成のままマイグレートした場合は自動生成されないため、5 件すべてを手動で作成します。自動生成された 2 件を使う場合は、管理画面で「有効」にチェックを入れ、必要ならプロバイダーを差し替えてください。

### 4-3. Langfuse プロンプト参照（`LangfusePromptRef`）

Langfuse 上のプロンプトを Django 側から参照するためのマッピングです。実体は Langfuse にあり、このモデルは名前・ラベル・フォールバックのみを持ちます。

| 項目 | 説明 |
|---|---|
| 識別名 | Django 内で一意な名前（例: `talk-morning-system`） |
| Langfuse プロンプト名 | Langfuse 上の実プロンプト名 |
| ラベル | 既定 `production` |
| フォールバックテキスト | Langfuse 未接続・プロンプト未登録時に使われるテキスト |

**HN Agent 用の 8 本は自動投入済みです。** `integrations/langfuse/migrations/0002_seed_default_refs.py` と `0003_seed_new_agent_refs.py` により、以下がフォールバックテキスト付きで作成されます。管理画面では**存在確認だけ**で構いません。

`hn-agent-orchestrator-system` / `-user`、`hn-agent-detective-system` / `-user`、`hn-agent-devils-advocate-system` / `-user`、`hn-agent-security-responder-system` / `-user`

**Talk 用は自動生成されません。** `TalkConfig` を新規作成しても参照は作られないため、プリセットごとに以下 2 本を**手動で作成**してください（命名は `features/talk/migrations/0012_migrate_system_prompt_to_ref.py` の規約に合わせます）。

- `talk-{設定名}-system` — システムプロンプト
- `talk-{設定名}-user` — ユーザープロンプト

Langfuse を使わない構成では、`Langfuse プロンプト名` に任意の名前を入れたうえで**フォールバックテキストに本文を書いておけば動作します**。フォールバックが空だと空のプロンプトで LLM を呼ぶことになります。

LLM 設定の詳細は [../django_api/integrations/llm/README.md](../django_api/integrations/llm/README.md) を参照してください。

## 5. 機能の設定

### 5-1. 会話生成設定（`TalkConfig`）

「AI ツール設定 → Talk Generator → 会話生成設定」から、プリセット単位で作成します（`morning`、`evening` など）。

| 項目 | 説明 |
|---|---|
| 設定名 | API の `config_name` に指定する一意な識別子 |
| 表示名 | 管理画面での表示名 |
| 予報区コード | 6 桁の数字（例: `130010`）。**プロンプトに `{{weather}}` を含める場合のみ必須** |
| TTS 設定 | 音声合成の有効化、モデル、スタイル、話速、フォーマット（既定 WAV） |
| システムプロンプト | 手順 4-3 で作った `talk-{設定名}-system` を選択 |
| ユーザープロンプト | 手順 4-3 で作った `talk-{設定名}-user` を選択 |

プロンプト参照 2 本はどちらも必須の外部キーです。`{{weather}}` `{{events}}` `{{datetime}}` はプロンプト本文に含まれていれば自動的に検出・展開されます（有効化フラグはありません）。

### 5-2. HN Agent 設定（`HNAgentConfig`）

| 項目 | 既定値 | 説明 |
|---|---|---|
| 有効 | OFF | **有効にできるのは 1 件のみ**（保存時に他が自動で無効化されます） |
| 推論深度 | `low` | Orchestrator の reasoning 量。モデルが非対応なら「無効」を選択 |
| スコア閾値 | 100 | 調査をトリガーするスコア |
| 速度閾値 | 50.0 | 調査をトリガーするスコア上昇速度（ポイント/時間） |
| ポーリング間隔（秒） | 600 | 最低 60。**実行スケジュールは制御しません**（手順 7 参照） |
| フロントページ取得件数 | 30 | Algolia API 経由で最大 1000 件程度まで指定可 |

加えて、**8 本のプロンプト参照を外部キーで選択します**（Orchestrator / Detective / Devil's Advocate / Security Responder × システム / ユーザー）。手順 4-3 で確認した自動投入済みのレコードをそのまま選べます。入力後、「有効」にチェックを入れて保存してください。

## 6. 外部サービスの設定

**使う機能のぶんだけ**設定します。3 つとも「有効にできるのは 1 件のみ」という制約があり、一覧画面のアクション「選択した設定を有効にする」からも切り替えられます（複数選択するとエラーになります）。

### 6-1. Microsoft Graph API 設定（`MSGraphConfig`）— OneDrive / Outlook 連携

証明書認証を使います。`テナント ID` / `クライアント ID` / `証明書サムプリント` / `対象ユーザー`（メールアドレス）に加え、**PEM 形式の秘密鍵**をテキストエリアに貼り付けます（暗号化保存。空のままなら既存の値を保持）。

> **Note:** リポジトリ直下の `secrets/django_api_graph_key.pem` は、**ここに貼り付ける PEM 秘密鍵のローカル置き場**です。`secrets/.gitignore` が `*` を指定しているため Git には追跡されず、Docker Compose にもマウントされません。アプリが読むのは DB に暗号化保存された値だけで、このファイルパスを参照する処理はありません。

### 6-2. Slack 通知設定（`SlackConfig`）— HN Agent のレポート送信先

`設定名` と Incoming Webhook URL（暗号化保存）を入力し、「有効」にします。未設定でも HN Agent は動作しますが、通知はスキップされます（ログに「Slack Webhook URLが未設定のため通知をスキップ」が出ます）。

### 6-3. Tavily API 設定（`TavilyConfig`）— Web 検索

`設定名`、API キー（暗号化保存）、`タイムアウト（秒）`（既定 30）を入力し、「有効」にします。

## 7. 定期実行の登録

HN Agent の定期実行は **`django-celery-beat` の定期タスクだけがトリガー**です。「外部サービス設定 → Celery」から登録します。

> **Note（罠）:** `HNAgentConfig.ポーリング間隔（秒）` は**実行スケジュールを制御しません**。ここを 600 秒にしても、定期タスクを登録しなければポーリングは一度も動きません。逆に、定期タスクを 5 分間隔で登録すれば 5 分ごとに実行されます。実際の間隔は必ず定期タスク側で設定してください。

1. **スケジュールを先に作る** — 「インターバル」で `10 分` のように作るか、「Cron スケジュール」で時刻を指定します（Cron のタイムゾーン既定は UTC）
2. **「定期タスク」を追加する** — 以下の 2 件を登録します

| タスク関数 | 用途 | キーワード引数（省略時の既定） |
|---|---|---|
| `hn_agent.poll_front_page` | HN フロントページを取得し、閾値超過スレッドを調査 | `{"auto_investigate": true}` |
| `hn_agent.cleanup_old_snapshots` | 古いスナップショットを削除 | `{"days": 90}` |

3. `タスク名` は任意の識別名、`タスク関数` に上表の文字列を入力し、`インターバル` または `Cron スケジュール` の**どちらか一方だけ**を選びます
4. 引数を既定値のまま使う場合、`キーワード引数` は空で構いません。変更する場合は JSON で入力します（例: `{"auto_investigate": false}`）
5. `有効` にチェックを入れて保存します

スケジューラは `celery-beat` コンテナが `DatabaseScheduler` で読み込むため、登録後の再起動は不要です。

## 8. 音声合成モデルの配置

TTS を使う場合は、Style-BERT-VITS2 のモデルファイルを配置します。手順は [../sbv2_api/README.md](../sbv2_api/README.md) を参照してください。

## 9. 動作確認チェックリスト

```bash
# 1. ヘルスチェック（認証不要）→ {"status":"ok"}
curl http://localhost:8000/health/

# 2. API ドキュメントが開くこと
open http://localhost:8000/swagger/

# 3. 管理画面にログインできること
open http://localhost:8000/admin/

# 4. トークン取得（email と password。username ではない）
curl -X POST http://localhost:8000/user/token/ \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "YOUR_PASSWORD"}'

# 5. Talk の設定一覧（Token 認証）
curl http://localhost:8000/talk/configs/ \
  -H "Authorization: Token YOUR_TOKEN"

# 6. 会話生成。TTS 有効時は audio_data（Base64）を含む JSON が返る
curl -X POST http://localhost:8000/talk/synthesize/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"config_name": "morning"}'

# 7. HN Agent の一括実行（スーパーユーザーのトークンが必要）
curl -X POST http://localhost:8000/hn-agent/run-all/ \
  -H "Authorization: Token YOUR_SUPERUSER_TOKEN"
```

- `/hn-agent/` 配下はすべて `IsAdminUser` のため、**スーパーユーザーのトークン**を使ってください。一般ユーザーのトークンでは 403 になります
- **Slack 通知の確認**は専用エンドポイントがないため、上記 7 の一括実行で閾値を超えたスレッドが調査されたときに、対象チャンネルへ投稿が届くかどうかで確認します。届かない場合は `docker compose logs -f celery-worker django-api` に Slack 関連の警告が出ていないか確認してください
- 定期実行の確認は、管理画面の「定期タスク」一覧で `最終実行日時` と `累計実行回数` が増えることで判断できます

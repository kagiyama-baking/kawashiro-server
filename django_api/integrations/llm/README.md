# LLM / Langfuse 統合（integrations/llm + integrations/langfuse）

LLM 接続・プロンプト管理・観測と、全エージェントで共有するプロンプト（Prompts）・スキル（Agent Skills）に関する **唯一の正（SSOT）** です。`integrations/llm`（Django アプリラベル `llm_config`）と `integrations/langfuse`（同 `langfuse_integration`）の 2 アプリをまとめて扱います。

## 1. 概要と 3 レイヤ責務分離

「どのモデルに繋ぐか」「どのテキストを渡すか」「いつ呼ぶか」を独立して差し替えられるよう、3 つのレイヤに分離しています。

| レイヤ | 責務 | 管理場所 | 実体 |
|---|---|---|---|
| **LLM 接続** | どのモデルに、どの鍵で繋ぐか | Django admin「AI設定」の「LLM設定」「サービス設定」 | `LLMProviderConfig` / `LLMServiceConfig` |
| **プロンプト管理** | どのテキストを渡すか | Django admin「AI設定」の「Prompts」「Agent Skills」+ Langfuse UI | `Prompt` / `AgentSkill`（どちらも全エージェントで共有）+ Langfuse 側のプロンプト実体 |
| **機能設定** | いつ・どのプロンプトで呼ぶか | Django admin「HackerNews Agent設定」「Companion 設定」「Talk 設定」 | `HNAgentConfig` / `CompanionConfig` / `TalkSetting` |

各機能の設定は、Prompts に登録したプロンプトを外部キーで選びます（HN Agent 設定の 8 本、Companion 設定・Talk 設定のシステムプロンプト）。スキル（Agent Skills）の本文だけは Prompts を通さず、スキル名とラベルで Langfuse から直接取ります（§4 の「Agent Skills」と §5）。各機能の設定は、登録したスキルから使うものを選びます（Companion 設定のスキルと、Talk 設定のシーン）。

モデルを差し替えるときは admin の「AI設定 → LLM設定」だけ、プロンプトを変えるときは Langfuse UI だけを触ればよく、コード変更もデプロイも不要です。

## 2. 構成要素

- **LiteLLM Proxy**（外部サービス / internal.kagiyama.net 管理）
  OpenAI 互換エンドポイント。`model_alias`（例: `bedrock/moonshotai.kimi-k2.5`）を受けて実プロバイダーへルーティングし、モデル差し替え・コスト集計・Virtual Key 発行を一元化します。接続先は環境変数 `LITELLM_PROXY_URL`（既定 `http://litellm-proxy:4000/v1`）。
- **Langfuse**（外部サービス / SaaS or self-hosted）
  LLM 呼び出しの観測（traces / generations / spans）と、バージョン管理付きプロンプトテンプレートを提供。環境変数 `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_BASE_URL` / `LANGFUSE_TRACING_ENVIRONMENT` で設定します。
- **`LLMProviderConfig`**（`integrations/llm/models.py`）
  モデルエイリアス + LiteLLM Virtual Key の組。複数の `LLMServiceConfig` から共有参照できます。
- **`LLMServiceConfig`**（同上）
  サービス（`orchestrator` / `detective` / `devils_advocate` / `security_responder` / `talk` / `companion`）ごとに、使用する `LLMProviderConfig`・有効フラグ・タイムアウトを割り当てます。
- **`AgentSkill`**（同上）
  全エージェントで共有するスキル（Agent Skills）。名前・説明・Langfuse のラベル・有効を持ち、各機能の設定が M2M で選びます（`CompanionConfig.skills` と、シーンとして選ぶ `TalkSetting.skills`）。本文は、スキル名と同じ名前の Langfuse の text プロンプトを `fetch_text_prompt` で直接取ります（§4）。取るのは `resolve_skill_body(skill)`（`integrations/llm/skills.py`。全エージェント共通）で、取れないか空なら `PromptUnavailableError`（`integrations/langfuse/exceptions.py`）です。
- **`Prompt`**（同上。admin の「AI設定 → Prompts」）
  全エージェントで共有するプロンプト。Django 内識別名 ↔ Langfuse プロンプト名のマッピング + `fallback_text`。`HNAgentConfig`（8 本）/ `TalkSetting` / `CompanionConfig`（システムプロンプト `system_prompt`）から FK で参照されます（§4 の「Prompts」）。
- **`get_llm_settings(service_name)`**（`integrations/llm/config.py`）
  `is_active=True` の `LLMServiceConfig` を引いて `LLMSettings` を返します。該当なしなら `LLMConfigurationError`。
- **実行基盤**（`integrations/llm/runtime.py`）
  `get_llm_settings` の結果で PydanticAI のエージェントを LiteLLM Proxy 経由で実行します（§6）。
- **`resolve_prompt(ref, **vars)` / `get_prompt_with_variables(ref)`**（`integrations/langfuse/client.py`。`ref` は `Prompt`）
  Langfuse から取得してコンパイル、失敗時は `fallback_text` を Mustache 風に簡易置換します。
- **`resolve_required_prompt(ref)`**（同上）
  `resolve_prompt` で本文を解決し、空（空白だけ）なら `PromptUnavailableError` にします（空のシステムプロンプトで続けない）。変数は展開しません。Companion と Talk 設定のシステムプロンプトが使います。
- **`fetch_text_prompt(name, *, label, variables=None)`**（同上）
  参照を使わず、Langfuse の Text 型プロンプトを名前とラベルで取り、本文を返します。`variables`（変数名 → 値の dict）を渡すと、本文の `{{変数}}` を SDK の compile で展開します（値は文字列にし、渡していない変数の `{{x}}` は残ります）。渡さなければ（`None`）compile せず、本文をそのまま返します。取れなければ（`langfuse` を import できない・届かない・未登録・Text 型でない）`LangfusePromptError` で、フォールバックはありません。SDK のプロンプトのキャッシュはそのまま使います。いまはスキルの本文（`resolve_skill_body`。変数は渡さない）だけが使います。
- **`langfuse_session(session_id)`**（同上）
  中で実行する処理のトレースと配下の観測に、Langfuse のセッション ID（`session.id`）を伝播する with 文です（`propagate_attributes` を包む）。入った時点の現在のスパン（`@observe` の関数の中ならそのスパン）にも付きます。`None`・空文字なら何もせず、伝播の開始・解除に失敗しても警告ログだけで本処理は続けます。いまは Talk のチャットと Companion が使います（§6 の「Langfuse の Sessions」）。

## 3. admin 設定と外部サービスの対応

```mermaid
flowchart LR
    subgraph Admin["Django admin"]
        subgraph LLMApp["AI設定（llm_config）"]
            Provider["LLM設定<br/>model_alias + Virtual Key"]
            Service["サービス設定<br/>orchestrator / detective /<br/>devils_advocate / security_responder /<br/>talk / companion"]
            Prompts["Prompts（Prompt）<br/>langfuse_prompt_name + label"]
            Skills["Agent Skills（AgentSkill）<br/>name + label"]
        end
        HN["HackerNews Agent設定"]
        Talk["Talk 設定（TalkSetting）"]
        Companion["Companion 設定（CompanionConfig）"]
    end

    subgraph External["外部サービス"]
        LiteLLM[("LiteLLM Proxy<br/>/v1/chat/completions")]
        Langfuse[("Langfuse<br/>get_prompt(name, label)")]
    end

    Service -->|provider_config| Provider
    HN -->|8本のプロンプト| Prompts
    HN -.->|orchestrator / detective /<br/>devils_advocate / security_responder| Service
    Talk -->|システムプロンプト 1 本| Prompts
    Talk -->|シーンに選ぶスキル| Skills
    Talk -.->|talk| Service
    Companion -->|システムプロンプト 1 本| Prompts
    Companion -->|使うスキルを選ぶ| Skills
    Companion -.->|companion| Service

    Provider ==>|Virtual Key + model_alias| LiteLLM
    Prompts ==>|名前とラベルで取得| Langfuse
    Skills ==>|name@label| Langfuse
```

- **枠「AI設定（llm_config）」**: admin で同じグループ（アプリ）に並ぶモデル。Prompts と Agent Skills は全エージェントで共有するので、機能のアプリではなくここに置く
- **実線**（admin 内）: FK 参照（設定 → Agent Skills は M2M）
- **破線**（admin 内）: `service_name` 経由の紐付け（FK ではなく文字列一致）
- **太線**（admin → 外部）: ランタイムで実際に叩く API

## 4. admin モデルリファレンス

### LLM設定（`LLMProviderConfig`）

| 項目 | 説明 |
|---|---|
| 設定名（`name`） | 識別名。**unique**（例: `Kimi K2.5 本番`, `GPT-4o テスト`） |
| モデルエイリアス（`model_alias`） | LiteLLM Proxy の `model_name`（例: `bedrock/moonshotai.kimi-k2.5`） |
| Virtual Key（`proxy_api_key`） | LiteLLM Virtual Key。**暗号化して保存**（DB カラム `encrypted_proxy_api_key`）。admin ではパスワード入力欄で、既存値は再表示されません |

> **Note:** Virtual Key を空にすると環境変数 `LITELLM_MASTER_KEY` にフォールバックします。マスターキーではなくサービス専用の Virtual Key を使うと、コスト上限の設定とアクセスログの識別が可能になります。

### サービス設定（`LLMServiceConfig`）

| 項目 | 説明 |
|---|---|
| サービス名（`service_name`） | `HN Agent Orchestrator` / `HN Agent Detective` / `HN Agent Devil's Advocate` / `HN Agent Security Responder` / `Talk` / `Companion` の 6 択（`Talk` の旧表示名は `Talk Generator`）。**unique**（1 サービス 1 レコード） |
| LLM設定（`provider_config`） | 使用する `LLMProviderConfig`。`on_delete=PROTECT` のため、参照中の設定は削除できません |
| 有効（`is_active`） | 既定 `True`。**`False` のレコードは `get_llm_settings` から見えず、設定なし扱いでエラーになります** |
| タイムアウト（`timeout`） | API リクエストのタイムアウト秒数（既定 `60`） |

> **Note:** `devils_advocate` / `security_responder` のレコードは migration `llm/0012` で `detective` を雛形として複製生成されます（`provider_config` と `timeout` を引き継ぎ、**`is_active=False`**）。detective が未設定の環境では何も生成されないため、admin から手動作成してください。いずれの場合も、使う前に有効化とプロバイダーの見直しが必要です。

> **Note:** `companion` のレコードは migration `llm/0013` で `talk` を雛形として複製生成されます（`provider_config` と `timeout` を引き継ぎ、**`is_active=False`**。`companion` が既にあれば変更しません）。talk が未設定の環境では何も生成されないため、admin から手動作成してください。いずれの場合も、使う前に有効化とプロバイダーの見直しが必要です。`0012` へ戻すと `companion` のレコードは削除されます。

> **Note（表示名）:** admin のグループ名は `apps.py` の `verbose_name`（「AI設定」。以前は「LLM設定」）で、migration はありません。サービス設定の表示名は migration `llm/0016` で「LLMサービス設定」から「サービス設定」に変えました（`AlterModelOptions`。表示名だけで DB は変えません）。「LLM設定」（`LLMProviderConfig`）とサービス設定の項目名「LLM設定」はそのままです。

### Prompts（`Prompt`）

全エージェントで共有するプロンプト（Langfuse の text プロンプトへの参照）です。admin の「AI ツール設定 → AI設定 → Prompts」で登録し、各機能の設定が外部キーで選びます（HN Agent 設定の 8 本と、Companion 設定・Talk 設定のシステムプロンプト `system_prompt`）。並び順は名前順です。

| 項目 | 説明 |
|---|---|
| 識別名（`name`） | Django 内で一意の名前。**unique**（例: `hn-agent-orchestrator-system`, `talk-morning-system`） |
| Langfuse プロンプト名（`langfuse_prompt_name`） | Langfuse 上の実プロンプト名。**識別名と一致するとは限りません**（§5 参照） |
| ラベル（`label`） | Langfuse のプロンプトラベル（既定 `production`。`staging` 等に切り替え可能） |
| フォールバックテキスト（`fallback_text`） | Langfuse 不達・未登録時に使うテキスト。`{{key}}` は呼び出し側の変数で簡易置換 |
| 説明（`description`） | 用途説明（admin 一覧に表示） |

- 設定のプロンプトの欄は、検索して選びます（autocomplete。識別名・Langfuse プロンプト名・説明が検索対象）。設定から選ばれているプロンプトは消せません（`on_delete=PROTECT`）。

> **Note（表名と内容の型）:** `Prompt` は langfuse_integration アプリの `LangfusePromptRef`（admin の「Langfuse → Langfuseプロンプト参照」）を移したモデルです。migration `llm/0018` が状態だけで作り、`hn_agent/0018`・`companion/0008`・`talk/0020` が設定の外部キーの向き先を替え、`langfuse_integration/0004` が古いモデルを状態から消します（表は変えません）。表は langfuse_integration の `0001` が作った `langfuse_integration_langfusepromptref`（`Meta.db_table`）のままです。既定の表名（`llm_config_prompt`）にそろえるなら、Agent Skills と合わせて後で `AlterModelTable` を足します。Companion 設定と Talk 設定の項目は `system_prompt_ref` から `system_prompt` に改めました（列は `system_prompt_ref_id` から `system_prompt_id` に変わり、値はそのまま）。権限と管理画面の履歴が指す内容の型（ContentType）の行は、`llm/0018` が `langfuse_integration`/`langfusepromptref` から `llm_config`/`prompt` へ付け替えます（id はそのまま。既定の権限の codename と表示名も `<操作>_prompt`・`Can <操作> Prompt` に改めます）。移す先の行もあれば、Agent Skills と同じ規則で 1 つにまとめます（下の「Agent Skills」の Note）。langfuse_integration アプリはモデルを持たなくなりますが（admin のグループも出ません）、これまでの migration（hn_agent・companion・talk の migration が依存する）のために残します。

> **Note（戻し方）:** 移す前の版へ戻すときは、先にこの版のコードで `python manage.py migrate llm_config 0017` を実行します（上の 5 本が外れ、列名と内容の型も元に戻ります）。イメージだけを古い版に戻すと、古い版のコードが `system_prompt_ref_id` の列を読むので、Companion と Talk のチャット（API と admin）が 500 になります。

### Agent Skills（`AgentSkill`）

全エージェントで共有するスキル（用途ごとの手順）です。admin の「AI ツール設定 → AI設定 → Agent Skills」で登録し、各機能の設定はその中から使うものを選びます（Companion 設定の「スキル」と、Talk 設定の「シーン」。1 つのスキルを複数の設定で選べます）。スキルは設定への外部キーを持ちません。並び順は名前順です。

| 項目 | 説明 |
|---|---|
| スキル名（`name`） | capability の id で、本文を読む Langfuse の text プロンプトの名前そのもの（例: `good-morning`）。**unique**。英小文字・数字をハイフンでつないだ形（`^[a-z0-9]+(-[a-z0-9]+)*\Z`）で 64 字以内。大文字・`_`・`:`・空白、先頭・末尾・連続のハイフンは不可。`instrumentation` は予約（下記） |
| 説明（`description`） | どんな発話のときに使うスキルか。Companion ではモデルが読んでスキルを選ぶための文なので、発話の例を含める（Talk のシーンでは、フロントの選択肢に出る人が読む短い文）。必須、1024 字以内（admin では複数行の入力欄） |
| ラベル（`label`） | 本文を取る Langfuse のプロンプトのラベル（既定 `production`。使い分けは [Companion の README の「Langfuse プロンプトのラベル」](../../features/companion/README.md#langfuse-プロンプトのラベル)） |
| 有効（`is_enabled`） | 既定 `True`。無効にしたスキルは、設定で選んでいても使わない |

- **スキル名がそのまま本文のプロンプト名です。** 本文は、スキル名と同じ名前の Langfuse の text プロンプトをスキルのラベルで読みます（接頭辞などは付けません）。名前を変えると本文を読むプロンプトも変わるので、Langfuse 側のプロンプト名も合わせてください。名前は capability の id と実行 API の `skill` の値も兼ねるので、変えると API で指定する値も変わります。本文の取り方（フォールバックなし・SDK のキャッシュ）は [Companion の README の「スキル」](../../features/companion/README.md#スキル) を参照してください。
- 表示（`__str__`）は `good-morning@staging`（スキル名@ラベル。本文を読むプロンプトとその版）です。設定のスキルの選択欄にそのまま出ます。
- 名前の規則は Agent Skills の命名規則（英小文字・数字・ハイフン、64 字以内）に合わせています。`:` を含められないので、PydanticAI の capability の id（`:` は使えない。予約の `deferred_capabilities` も `_` を含むので通らない）にそのまま使えます。Langfuse のプロンプト名にはこの規則より多くの文字を使えるので、スキルの本文のプロンプトは、この規則に合う名前で作ってください。
- **`instrumentation` は予約しています。** `apps.py` の `Agent.instrument_all` により、どの実行にも PydanticAI の Instrumentation（id: `instrumentation`）が入るため、同じ id のスキルを渡すと id の衝突で実行そのものが失敗します（`tests/integrations/llm/test_agent_skill.py` で確認）。
- 説明を `TextField` ではなく `CharField` にしているのは、`full_clean()` で字数の上限を確かめるためです（`TextField` の `max_length` はフォームの入力欄にしか効きません）。
- `save()` は `full_clean()` を呼びます。登録済みの名前で追加すると、admin では名前の欄のエラーになり保存されません。
- **Talk のチャットで使ったスキルは消せません**（チャットセッションがシーンとして `on_delete=PROTECT` で参照する）。使わなくなったら無効にしてください。設定で選んでいるだけのスキルは消せ、選択から外れます。
- admin の一覧には名前・ラベル・有効が並び、有効とラベルで絞り込め、名前と説明で検索できます（名前がそのままプロンプト名なので、プロンプト名の列はありません）。

> **Note（表名と内容の型）:** `AgentSkill` は Companion のアプリから移したモデルです（migration `llm/0014` と `companion/0006`。どちらも表は変えません）。表は companion の `0003` が作った `companion_agentskill`（`Meta.db_table`）、設定の選択の中間表は `companion_companionconfig_skills` のままです。既定の表名（`llm_config_agentskill`）にそろえるなら、後で `AlterModelTable` を足します。権限と管理画面の履歴が指す内容の型（ContentType）の行は、`llm/0014` が companion から llm_config へ付け替えます（id はそのままなので、付けた権限と履歴は移したモデルでも見えます。companion の行がなければ何もしません）。llm_config の行もあれば（戻した状態で新しいコードが作った行など）、その行を指す履歴と権限の付与（グループ・ユーザー）を元の行へ寄せてから消し、1 つにまとめます。戻すときも同じ規則で companion に戻します。移す前の版へ戻す手順は [Companion の README の「構成」](../../features/companion/README.md#構成) を参照してください。

> **Note（名前の付け替え）:** migration `llm/0015` で、スキル名をプロンプト名そのものにしました。それまで本文は `companion-skill-<スキル名>` から読んでいたので、前進では、読む先を変えないよう、既存の全部の行の名前に接頭辞 `companion-skill-` を付けます（例: `good-morning` → `companion-skill-good-morning`。Langfuse 側は変えません）。付け替えると、capability の id と実行 API の `skill` の値も接頭辞付きの名前になります。接頭辞を付けると 64 字を超える名前（49 字以上）が 1 件でもあれば、何も変えずに `RuntimeError` で止まります（起動時の migrate が止まるので、その名前を 48 字以内にし、Langfuse のプロンプト名も `companion-skill-<新しい名前>` に合わせてから起動し直します）。戻すと、接頭辞の付いた名前からだけ外し、接頭辞のない名前（`0015` の後に登録したスキル）は変えません（戻した後は `companion-skill-<名前>` を読みます）。外した名前のスキルがすでにあるか、外した名前が予約した名前（`instrumentation`）になるなら、何も変えずに `RuntimeError` で止まります。

## 5. Langfuse プロンプト命名規約

Django 側の識別名と Langfuse 側のプロンプト名は別物です。HN Agent の **system プロンプトのみ Langfuse 側に `-system` が付きません**（歴史的経緯）。

| 用途 | Django 識別名（`name`） | Langfuse プロンプト名 |
|---|---|---|
| HN Agent Orchestrator system | `hn-agent-orchestrator-system` | `hn-agent-orchestrator` |
| HN Agent Orchestrator user | `hn-agent-orchestrator-user` | `hn-agent-orchestrator-user` |
| HN Agent Detective system | `hn-agent-detective-system` | `hn-agent-detective` |
| HN Agent Detective user | `hn-agent-detective-user` | `hn-agent-detective-user` |
| HN Agent Devil's Advocate system | `hn-agent-devils-advocate-system` | `hn-agent-devils-advocate` |
| HN Agent Devil's Advocate user | `hn-agent-devils-advocate-user` | `hn-agent-devils-advocate-user` |
| HN Agent Security Responder system | `hn-agent-security-responder-system` | `hn-agent-security-responder` |
| HN Agent Security Responder user | `hn-agent-security-responder-user` | `hn-agent-security-responder-user` |
| Companion system | `companion-system` | `companion-system`（同名） |
| Talk 設定（`TalkSetting`）の system | 自由（migration `talk/0018` が作った Talk 設定は、旧プリセットのシステムプロンプトの参照（例: `talk-morning-system`）をそのまま使う） | 参照の `langfuse_prompt_name` |
| スキル（Agent Skills）の本文 | なし（参照を作らない） | スキル名そのもの（例: `good-morning`。ラベルはスキルの `label`） |

**投入方法の違いに注意してください。**

- **HN Agent の 8 本**は migration `langfuse/0002`（orchestrator / detective の 4 本）と `langfuse/0003`（devils_advocate / security_responder の 4 本 + orchestrator system の `fallback_text` を V2 へ更新）で、`fallback_text` 入りのプロンプト（当時の `LangfusePromptRef`。いまの `Prompt`）として自動投入されます。
- **Companion のシステムプロンプトの参照は自動生成されません。** リポジトリを公開しているので本文を git に置かず、migration はありません。Langfuse の text プロンプトと `Prompt`（`companion-system`）を手動で作成してから `CompanionConfig.system_prompt` に割り当てます。
- **Talk 設定のシステムプロンプトの参照も手動作成です**（migration はありません。`talk/0018` は既存のチャットのために Talk 設定を作りますが、参照は旧プリセットのものをそのまま使います）。
- **スキル（Agent Skills）の本文には参照を作りません。** Langfuse に本文の text プロンプトを作り、そのプロンプト名をスキル名として admin の Agent Skills に登録します（`fetch_text_prompt` でスキルのラベルの版を取る。**フォールバックはなく**、Companion では取れなければ 503）。ラベルの使い分けは [Companion の README の「Langfuse プロンプトのラベル」](../../features/companion/README.md#langfuse-プロンプトのラベル)、登録の順序は [../../../docs/initial-setup.md](../../../docs/initial-setup.md) の 5-2 を参照してください。

いずれの場合も、`Prompt` があるのは Django 側のマッピングだけです。Langfuse 側にプロンプト実体を登録すると、Langfuse UI 上でバージョン管理・A/B テスト・`staging`/`production` ラベル切り替えが可能になります。参照のプロンプトは、未登録でも `fallback_text` で動作します（スキルの本文は参照を通さないので、Langfuse への登録が必要です）。

## 6. LLM の呼び出し方

LLM 呼び出しはすべて PydanticAI のエージェントで行います。エージェントは各機能のモジュールに定義し（`features/talk/llm_agents.py`、`features/hn_agent/orchestrator.py`、`features/hn_agent/agents/*.py`、`features/companion/agent.py`）、実行は `integrations/llm/runtime.py` を通します。モデル名も API キーもコードに書きません。

```python
from pydantic_ai import Agent

from integrations.langfuse.client import resolve_prompt
from integrations.llm.config import get_llm_settings
from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMOutputError,
    LLMTimeoutError,
)
from integrations.llm.runtime import run_agent_sync

# None を許すと、本文のない応答を再試行せず None として受け取れる
MY_AGENT = Agent(name="my-feature", output_type=str | None)

try:
    settings = get_llm_settings("talk")  # admin のサービス設定を解決（DB を読む）
    system_prompt = resolve_prompt(config.system_prompt)
    user_prompt = resolve_prompt(config.user_prompt, weather="晴れ")

    result = run_agent_sync(
        MY_AGENT, settings, user_prompt=user_prompt, instructions=system_prompt
    )
    text = result.output or ""
except LLMConfigurationError:
    ...  # サービス設定が無い、または is_active=False
except LLMTimeoutError:
    ...  # timeout（既定 60 秒）か run_timeout の超過
except LLMOutputError:
    ...  # 応答が期待する形にならなかった（出力リトライ後も不正など）
except LLMClientError:
    ...  # 接続失敗・HTTP エラー（429 / 5xx など）・利用上限の超過
```

| 関数 | 用途 |
|---|---|
| `run_agent_sync(agent, settings, *, user_prompt, instructions, message_history, deps, usage_limits, max_tokens, retries, conversation_id, reasoning_effort, capabilities, run_timeout)` | 同期コードから実行する。Talk のタイトル、Orchestrator、Companion はこちら |
| `arun_agent(...)`（引数は同じ） | イベントループ上から `await` する。サブエージェントはこちら |
| `stream_text_sync(agent, settings, *, user_prompt, deps, message_history, max_tokens, conversation_id)` | 同期コードから実行し、本文の増分を順に返すジェネレータ。Talk のチャットはこちら |
| `open_model(settings)` | `AsyncOpenAI` を作って閉じる async context manager。接続はイベントループに属するので、実行ごとに作る |
| `translate_llm_errors()` | PydanticAI の例外を上の 3 種へ変換する。`RunCancelled` と `UserError` は変換しない |

- **`agent.run_sync` は使いません。** そちらでは `sync_to_async(thread_sensitive=True)` が呼び出し元スレッドに戻らず、別の DB 接続になります（トランザクション内のデータも見えません）。`run_agent_sync` は `asgiref.async_to_sync` で実行するので、ツール内の `sync_to_async` は呼び出し元スレッドで動きます。
- **ストリーミングは `stream_text_sync` を通します。** `Agent.run_stream_sync` の同期ブリッジは 1 本の長寿命タスクで実行全体を動かすので、OpenTelemetry のネストとキャンセルスコープが保たれます。呼び出し元スレッドのイベントループで動くので、同じスレッドで読み進めて閉じます（`AsyncOpenAI` も同じループで閉じます）。`close()` すると LiteLLM への HTTP 接続もその場で閉じます。`run_stream_sync` に `instructions` の引数がないので、system プロンプトはエージェントの動的 instructions（`deps` を返す関数）で渡します。増分は 50 ms 幅でまとめます。
- **イベントループ上で ORM に触れません。** async のツールやメソッドでは、ORM・HN/Tavily 取得・プロンプト解決を同期関数にまとめて `await sync_to_async(...)` で実行します（`features/hn_agent/agents/*.py` の `_prepare`）。同期のツールの中から `run_sync` は呼べないので、ツールは `async def` にします。
- **LiteLLM との送受信**: LiteLLM のモデル名は DB 上の任意の文字列なので、名前から推定されるプロファイルに送受信を左右させません（`_LITELLM_PROFILE`）。どのエイリアスでも、出力上限は `max_tokens`（`drop_params` で `max_completion_tokens` が黙って落ちるのを避ける）で送り、`response_format`・tools の `strict`・推論テキストの送り返し・system プロンプトへの追記やロールの変更はありません。応答本文は `<think>` などの文字列も含めてそのまま受け取ります。`service_name` と `environment` は `extra_body.metadata` に付与します。推論深度は `reasoning_effort` を指定したときだけ `reasoning_effort` で送ります（PydanticAI の `openai_reasoning_effort`。`None` と空文字は送りません。今は HN Agent の Orchestrator だけが指定します）。契約は `tests/integrations/llm/test_runtime.py` で固定しています。
- **本文のない応答**: 出力上限（`length`）やフィルター（`content_filter`）で本文がなくなった応答も例外にせず、本文なしとして扱います（`_TreatEmptyResponseAsFinished`）。`output_type` に `None` を許すエージェントはそのまま `None` を受け取り、再試行しません。`stream_text_sync` では増分なしで正常に終わります。
- **実行ごとの capability**: `run_agent_sync` / `arun_agent` の `capabilities` は `_TreatEmptyResponseAsFinished` の後ろに足すので、本文のない応答の扱いは変わりません。遅延しないものの指示は、実行の `instructions` より前の別の system メッセージになります。`defer_loading=True`（オンデマンド）のものは、system には一覧（PydanticAI の英語の定型文と id・説明）だけが載り、モデルが組み込みの `load_capability` ツールで読み込みます。このプロジェクトのプロファイル（`supports_inline_system_prompts=True`）では、読み込んだ指示は tool の結果の直後に会話途中の `role: system` メッセージとして送られます（tool の結果には入りません）。契約は `tests/integrations/llm/test_runtime.py` で固定しています。
- **トレーシング**: `apps.py` の `ready()` で `Agent.instrument_all(InstrumentationSettings())` を呼び、呼び出しは Langfuse の generation として記録されます（名前は `chat <model_alias>`）。設定は 1 つを共有します。引数なしの `instrument_all()` は実行のたびに設定を作り、MeterProvider が未設定の間は OpenTelemetry 側に Meter がたまり続けます。呼び出し側の関数は `@observe(name="talk/chat")` 等でトレースをまとめます（Sessions へのまとめ方は次の項目）。`langfuse.openai` は import するだけで OpenAI SDK を書き換えて generation が二重になるので、使わないでください。
- **Langfuse の Sessions**: `session.id` を付けたトレースは、そのセッションにまとまります。付けるには、処理を共有の `langfuse_session`（`integrations/langfuse/client.py`。§2）の中で実行します。Talk のチャットはチャットセッションの UUID、Companion は `companion/<日本時間の日付>`（1 日に 1 つ。朝・夜の自動化などその日の実行をまとめる）です。Langfuse は `gen_ai.conversation.id` もセッションとして扱います。PydanticAI の既定は実行ごとの UUID でセッションが増え続けるので、`arun_agent` と `stream_text_sync` の `conversation_id` は省略時にサービス名とし、HN Agent は `hn-thread/<hn_id>` を渡して 1 スレッドの調査を 1 セッションにまとめます。`session.id` を伝播していれば（Talk のチャット・Companion）そちらが優先されます。
- **usage の内訳**: LiteLLM の `text_tokens` と `reasoning_tokens` は output の内数ですが、Langfuse は usage の全項目を足して total にします。二重に数えないよう、`_LiteLLMChatModel`（ストリーミングは `_LiteLLMStreamedResponse`）で内訳を除いています。計装はプロバイダーとの境界の usage を読むので、capability の `after_model_request` で書き換えても反映されません。
- **タイムアウト**: `LLMServiceConfig.timeout`（既定 60 秒）が OpenAI クライアントに渡ります。1 リクエストごとの上限で、コード側でハードコードしません。ツールを使う実行はリクエストを何度も送るので、合計に上限が要る呼び出し側は、`run_agent_sync` / `arun_agent` の `run_timeout`（秒。PydanticAI の `timeout=`）で実行全体の制限時間を指定します（省略時は制限なし。今は Companion だけが指定します）。過ぎると `LLMTimeoutError` です。モデルの応答待ちはその場で止まりますが、ツールが `sync_to_async` で動かしている同期処理は途中で止められないので、それが終わってから止まります。`stream_text_sync` には実行全体の制限はありません。
- **テスト**: 書き方は [../../../.claude/CLAUDE.md](../../../.claude/CLAUDE.md) の「LLM 呼び出しのテスト」を参照してください。

## 7. フェイルソフト挙動

外部サービスが落ちても機能全体は止まらない設計です。

| 状況 | 挙動 |
|---|---|
| Langfuse 未設定 / 接続失敗 / プロンプト未登録（`Prompt` 経由のプロンプト） | `fallback_text` を使用し、`{{key}}` を `render_template` で簡易置換。警告ログのみで処理継続 |
| Langfuse 側が Chat 型プロンプト | 未対応のため警告ログを出して `fallback_text` にフォールバック（対応しているのは Text 型のみ） |
| `langfuse` パッケージ未インストール | `ImportError` を捕捉して `fallback_text` にフォールバック |
| Langfuse への `session_id` 付与失敗 | 警告ログのみ。Talk のチャットも Companion の実行も継続 |
| Agent Skill（Companion のスキル・Talk のシーン）の本文を Langfuse から取れない（届かない・未登録・Chat 型）か、空 | **フェイルソフトしません。** `PromptUnavailableError` で実行（Talk ではそのターン）を止め、API は 503（フォールバックなし）。SDK のキャッシュに一度取れた本文があれば、取り直しに失敗しても古い本文で動き続ける（[Companion の README の「スキル」](../../features/companion/README.md#スキル)） |
| Companion・Talk 設定のシステムプロンプトの本文が空（Langfuse から取れず `fallback_text` も空） | **フェイルソフトしません。** `resolve_required_prompt` が `PromptUnavailableError` にし、API は 503（空のシステムプロンプトで話さない） |
| Companion の出力（セリフと使ったスキル）を Langfuse のスパンに記録できない | 警告ログのみ。実行は続け、API はセリフを返す（[Companion の README の「トレース（Langfuse）」](../../features/companion/README.md#トレースlangfuse)） |
| `LLMProviderConfig` の Virtual Key 未設定 | 環境変数 `LITELLM_MASTER_KEY` にフォールバック。それも未設定ならプレースホルダーのキーで送信し、認証の判断は LiteLLM Proxy に任せる |
| `LLMServiceConfig` が無い / `is_active=False` | `LLMConfigurationError`（**ここはフェイルソフトしません**。設定漏れは早期に顕在化させます） |

> **Note（pgvector）**: PostgreSQL の `vector` 拡張は migration `core/0002` で有効化され、`pgvector` パッケージも依存に残っています（過去のマイグレーションが import しているため）。ただし **現在 `VectorField` を持つモデルは 1 つもありません**。ベクトル検索機能は稼働していないので、拡張の存在をもって RAG が動いていると誤解しないでください。

## 8. 関連ドキュメント

| ドキュメント | 内容 |
|---|---|
| [../../features/hn_agent/README.md](../../features/hn_agent/README.md) | HN Agent の構成・`HNAgentConfig`・8 本のプロンプト割り当て |
| [../../features/talk/README.md](../../features/talk/README.md) | Talk 設定（システムプロンプトとシーン）・チャットセッション |
| [../../features/companion/README.md](../../features/companion/README.md) | Companion の `CompanionConfig`（Agent Skills から使うスキルを選ぶ）・スキルの本文の取得・実行の流れと API・Langfuse プロンプトのラベル・`AgentSkill` を移す migration の戻し方 |
| [../../../docs/initial-setup.md](../../../docs/initial-setup.md) | 初回セットアップ手順（admin 設定・環境変数の投入順） |
| [../../README.md](../../README.md) | Django API 全体構成 |

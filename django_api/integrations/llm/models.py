"""LLM API設定モデルと、全エージェントで共有するプロンプト（Prompts）・スキル（Agent Skills）のモデル."""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from core.encryption import decrypt_value, encrypt_value


class LLMProviderConfig(models.Model):
    """LLMプロバイダー設定（モデル + Virtual Key）.

    モデルエイリアスとAPIキーの組み合わせを管理する。
    複数のLLMServiceConfigから共有して参照できる。
    """

    name = models.CharField(
        "設定名",
        max_length=100,
        unique=True,
        help_text="この設定の識別名（例: Kimi K2.5 本番, GPT-4o テスト）",
    )
    model_alias = models.CharField(
        "モデルエイリアス",
        max_length=100,
        help_text="LiteLLM Proxyのmodel_name（例: bedrock/moonshotai.kimi-k2.5）",
    )
    _encrypted_proxy_api_key = models.TextField(
        "暗号化されたAPIキー",
        blank=True,
        default="",
        db_column="encrypted_proxy_api_key",
        help_text="LiteLLM Virtual Key（未設定時はLITELLM_MASTER_KEY環境変数を使用）",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "LLM設定"
        verbose_name_plural = "LLM設定"

    def __str__(self):
        return f"{self.name}（{self.model_alias}）"

    @property
    def proxy_api_key(self) -> str:
        """Virtual Keyを復号化して取得（未設定時は空文字列）."""
        return decrypt_value(self._encrypted_proxy_api_key)

    @proxy_api_key.setter
    def proxy_api_key(self, value: str):
        """Virtual Keyを暗号化して保存."""
        self._encrypted_proxy_api_key = encrypt_value(value)


class LLMServiceConfig(models.Model):
    """サービスごとのLLM設定割り当て.

    各サービスがどのLLMプロバイダー設定を使用するかを管理する。
    """

    SERVICE_CHOICES = [
        ("orchestrator", "HN Agent Orchestrator"),
        ("detective", "HN Agent Detective"),
        ("devils_advocate", "HN Agent Devil's Advocate"),
        ("security_responder", "HN Agent Security Responder"),
        ("talk", "Talk"),
        ("companion", "Companion"),
    ]

    service_name = models.CharField(
        "サービス名",
        max_length=50,
        unique=True,
        choices=SERVICE_CHOICES,
        help_text="LLMを使用するサービスの識別名",
    )
    provider_config = models.ForeignKey(
        LLMProviderConfig,
        on_delete=models.PROTECT,
        verbose_name="LLM設定",
        help_text="使用するLLMプロバイダー設定を選択",
    )
    is_active = models.BooleanField(
        "有効",
        default=True,
        help_text="このサービス設定を有効にする",
    )
    timeout = models.IntegerField(
        "タイムアウト（秒）",
        default=60,
        help_text="APIリクエストのタイムアウト秒数",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "サービス設定"
        verbose_name_plural = "サービス設定"

    def __str__(self):
        return f"{self.get_service_name_display()} → {self.provider_config.name}"


# プロンプト名の規則（Langfuse のプロンプト名そのもの）。前後の空白と改行は不可で、Langfuse の
# フォルダの `/` と途中の空白は使える。`.` は改行に合わないので途中の改行も通らない。`$` は末尾の
# 改行も通すので `\Z` で終える。
PROMPT_NAME_PATTERN = r"^\S(?:.*\S)?\Z"


class Prompt(models.Model):
    """プロンプト（Langfuse の text プロンプト。全エージェントで共有する）.

    名前は Langfuse のプロンプト名そのもので、本文はその名前の text プロンプトを `label` で取る
    （`integrations/llm/prompts.py` の `resolve_prompt_text`。フォールバックはない）。各機能の
    設定（HN Agent の 8 本、Companion 設定・Talk 設定のシステムプロンプト）が外部キーで選ぶ。
    """

    name = models.CharField(
        "プロンプト名",
        max_length=200,
        unique=True,
        validators=[
            RegexValidator(
                regex=PROMPT_NAME_PATTERN,
                message="プロンプト名の前後には、空白と改行を入れられません（途中の改行も不可）",
            ),
        ],
        help_text=(
            "本文を取る Langfuse の text プロンプトの名前そのもの（例: hn-agent-orchestrator。"
            "フォルダは / で区切る）。200 字以内。前後の空白と改行は使えない。名前を変えると"
            "本文を取る先も変わる"
        ),
    )
    label = models.CharField(
        "ラベル",
        max_length=50,
        default="production",
        help_text="本文を取る Langfuse のプロンプトのラベル（staging / production）",
    )
    description = models.CharField(
        "説明",
        max_length=255,
        blank=True,
        default="",
        help_text="このプロンプトの用途（admin の一覧に出る）",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "Prompt"
        verbose_name_plural = "Prompts"
        ordering = ["name"]
        # langfuse_integration から状態だけの migration（llm_config 0018・langfuse_integration
        # 0004）で移したので、表は langfuse_integration の 0001 が作ったまま。既定の表名
        # （llm_config_prompt）にそろえるなら、後で AlterModelTable を足す。
        db_table = "langfuse_integration_langfusepromptref"

    def __str__(self) -> str:
        return f"{self.name}@{self.label}"

    def save(self, *args, **kwargs):
        """保存時にバリデーションを実行."""
        self.full_clean()
        super().save(*args, **kwargs)


# スキル名の規則（Agent Skills の命名: 英小文字・数字・ハイフン。先頭・末尾・連続のハイフンは不可）。
# スキル名は PydanticAI の capability の id になるので、id に使えない `:` も、予約の
# `deferred_capabilities` も通らない。`$` は末尾の改行も通すので `\Z` で終える。
SKILL_NAME_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*\Z"

# 毎回の実行に入る組み込みの capability の id（`integrations/llm/apps.py` の
# `Agent.instrument_all` が入れる Instrumentation）。スキル名が同じだと id が衝突し、
# そのスキルを渡した実行は始まる前に失敗する。
RESERVED_SKILL_NAMES = frozenset({"instrumentation"})


def validate_skill_name_not_reserved(value: str) -> None:
    """組み込みの capability と同じ id になるスキル名を拒む."""
    if value in RESERVED_SKILL_NAMES:
        raise ValidationError(
            "「%(value)s」は予約されているため、スキル名に使えません",
            code="reserved",
            params={"value": value},
        )


class AgentSkill(models.Model):
    """エージェントのスキル（Agent Skills。用途ごとの手順）.

    全エージェントで共有する（Companion 設定が使うスキルを `CompanionConfig.skills` で、
    Talk 設定が選べるシーンを `TalkSetting.skills` で選ぶ）。Companion では名前と説明が
    モデルに見せる一覧になり、Talk では説明がフロントの選択肢になる。本文はそのスキルを
    使うときだけ、スキル名と同じ名前の Langfuse の text プロンプトを `label` で取る
    （フォールバックはない）。
    """

    name = models.CharField(
        "スキル名",
        max_length=64,
        unique=True,
        validators=[
            RegexValidator(
                regex=SKILL_NAME_PATTERN,
                message=(
                    "スキル名は英小文字・数字をハイフンでつないだ形で入力してください"
                    "（例: good-morning）"
                ),
            ),
            validate_skill_name_not_reserved,
        ],
        # help_text は管理画面で HTML として出るので、山かっこを書かない
        help_text=(
            "英小文字・数字・ハイフン（例: good-morning）、64 字以内。"
            "先頭・末尾・連続のハイフンは使えない。名前は、本文を読む Langfuse の text "
            "プロンプトの名前そのもの（版はラベルで選ぶ）なので、名前を変えると本文を読む先も"
            "変わる"
        ),
    )
    description = models.CharField(
        "説明",
        max_length=1024,
        help_text=(
            "どんな発話のときに使うスキルか（例: 朝のあいさつ。「おはよう」など）。"
            "モデルはこの説明を読んで使うスキルを選ぶ。1024 字以内"
        ),
    )
    label = models.CharField(
        "ラベル",
        max_length=50,
        default="production",
        help_text="本文を取る Langfuse のプロンプトのラベル（staging / production）",
    )
    is_enabled = models.BooleanField(
        "有効",
        default=True,
        help_text="無効にしたスキルは、設定で選んでいても使わない",
    )

    class Meta:
        verbose_name = "Agent Skill"
        verbose_name_plural = "Agent Skills"
        ordering = ["name"]
        # companion から状態だけの migration（llm_config 0014・companion 0006）で移したので、
        # 表は companion の 0003 が作った companion_agentskill のまま。既定の表名
        # （llm_config_agentskill）にそろえるなら、後で AlterModelTable を足す。
        db_table = "companion_agentskill"

    def __str__(self) -> str:
        return f"{self.name}@{self.label}"

    def save(self, *args, **kwargs):
        """保存時にバリデーションを実行."""
        self.full_clean()
        super().save(*args, **kwargs)

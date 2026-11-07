"""プロンプト（Prompt）の migration のテストの共通の時点・名前・ヘルパ.

移設（llm_config 0018・hn_agent 0018・companion 0008・talk 0020・langfuse_integration 0004）の
テストは tests/integrations/llm/test_prompt_move_migrations.py、名前の付け替え
（llm_config 0019）のテストは test_prompt_rename_migrations.py。migration を行き来する
フィクスチャ（`prompt_migrator`）は tests/integrations/llm/conftest.py。
"""

from django.conf import settings
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Q

from tests.fixtures.migrations import prompt_model, system_prompt_field

# 移す前の時点（プロンプトは langfuse_integration の LangfusePromptRef）。戻し方は llm_config 0017
LLM_BEFORE_MOVE = ("llm_config", "0017_alter_llmserviceconfig_service_name")
BEFORE_MOVE = [
    LLM_BEFORE_MOVE,
    ("hn_agent", "0017_make_new_agent_prompt_refs_required"),
    ("companion", "0007_alter_companionconfig_skills_related_name"),
    ("talk", "0019_delete_talkconfig_remove_chatsession_config_name"),
    ("langfuse_integration", "0003_seed_new_agent_refs"),
]
ROLLBACK = [LLM_BEFORE_MOVE]
# 移す migration（langfuse_integration の 0004 は、HN Agent・Companion・Talk の付け替えの後）
MOVE = ("llm_config", "0018_move_prompt_from_langfuse_integration")
HN_RETARGET = ("hn_agent", "0018_prompt_fks_to_llm_config")
COMPANION_RENAME = ("companion", "0008_rename_system_prompt_ref_to_system_prompt")
TALK_RENAME = ("talk", "0020_rename_system_prompt_ref_to_system_prompt")
DELETE_OLD = ("langfuse_integration", "0004_delete_langfusepromptref")
AFTER_MOVE = [DELETE_OLD]
MOVE_MIGRATIONS = {MOVE, HN_RETARGET, COMPANION_RENAME, TALK_RENAME, DELETE_OLD}
# 名前を Langfuse のプロンプト名にする migration と、その前後（前は移した後の時点）
RENAME = ("llm_config", "0019_prompt_name_is_langfuse_prompt_name")
BEFORE_RENAME = [MOVE, DELETE_OLD]
AFTER_RENAME = [RENAME]
ALL_MIGRATIONS = {*MOVE_MIGRATIONS, RENAME}
# 0019 が付け替えの途中に使う一時の名前の接頭辞
TEMPORARY_PREFIX = "__llm_config_0019__/"

# HN Agent 設定がプロンプトを選ぶ 8 本の外部キー
HN_PROMPT_FIELDS = (
    "orchestrator_system_prompt",
    "orchestrator_user_prompt",
    "detective_system_prompt",
    "detective_user_prompt",
    "devils_advocate_system_prompt",
    "devils_advocate_user_prompt",
    "security_responder_system_prompt",
    "security_responder_user_prompt",
)

# テストで作る設定とプロンプト。後始末では、名前（Langfuse のプロンプト名も）がこの接頭辞か
# 一時の名前の接頭辞で始まるプロンプトを消す
CONFIG_NAME = "prompt-move-test"
TEST_PREFIX = "prompt-move-test-"
SYSTEM_PROMPT_NAME = f"{TEST_PREFIX}system"
HN_PROMPT_NAMES = tuple(f"{TEST_PREFIX}hn-{field}" for field in HN_PROMPT_FIELDS)
# 権限と管理画面の履歴を付ける、テスト用のユーザーとグループ
TEST_USER_EMAIL = "prompt-move-test@example.com"
TEST_GROUP_NAME = "prompt-move-test"


def delete_test_rows(apps) -> None:
    """テストで作った行を消す（プロンプトは設定から PROTECT で参照されるので、設定を先に）."""
    apps.get_model("hn_agent", "HNAgentConfig").objects.filter(
        name=CONFIG_NAME
    ).delete()
    apps.get_model("companion", "CompanionConfig").objects.filter(
        name=CONFIG_NAME
    ).delete()
    apps.get_model("talk", "TalkSetting").objects.filter(name=CONFIG_NAME).delete()
    prompt_model(apps).objects.filter(
        Q(name__startswith=TEST_PREFIX) | Q(name__startswith=TEMPORARY_PREFIX)
    ).delete()
    # ユーザーを消すと、そのユーザーの履歴と権限の付与も消える
    apps.get_model(settings.AUTH_USER_MODEL).objects.filter(
        email=TEST_USER_EMAIL
    ).delete()
    apps.get_model("auth", "Group").objects.filter(name=TEST_GROUP_NAME).delete()


def migrate_to(migrator, targets):
    """targets まで当て（戻し）、その時点のモデルを引ける apps を返す."""
    migrator.loader.build_graph()
    migrator.migrate(targets)
    return migrator.loader.project_state(targets).apps


def applied_migrations() -> set:
    """DB に当たっている migration."""
    return set(MigrationRecorder(connection).applied_migrations())


def create_prompt(apps, name: str, **fields):
    """その時点のモデルでプロンプトを作る.

    0019 より前のモデルでは、Langfuse のプロンプト名を指定しなければ名前と同じにする。
    """
    model = prompt_model(apps)
    if has_field(model, "langfuse_prompt_name"):
        fields.setdefault("langfuse_prompt_name", name)
    return model.objects.create(name=name, **fields)


def has_field(model, name: str) -> bool:
    """モデルにその項目があるか."""
    return name in {field.name for field in model._meta.get_fields()}


def names_by_pk(apps, pks) -> dict[int, str]:
    """その時点のモデルで、プロンプトの pk → 名前."""
    return dict(prompt_model(apps).objects.filter(pk__in=pks).values_list("pk", "name"))


def create_configs(apps) -> dict[str, int]:
    """その時点のモデルで、プロンプトを選んだ HN Agent 設定・Companion 設定・Talk 設定を作る.

    Returns:
        項目（HN Agent の 8 本と、Companion・Talk のシステムプロンプト）→ 選んだプロンプトの pk
    """
    hn_prompts = {
        field: create_prompt(apps, name)
        for field, name in zip(HN_PROMPT_FIELDS, HN_PROMPT_NAMES, strict=True)
    }
    apps.get_model("hn_agent", "HNAgentConfig").objects.create(
        name=CONFIG_NAME, **hn_prompts
    )
    system_prompt = create_prompt(apps, SYSTEM_PROMPT_NAME)
    for app_label, model_name in (
        ("companion", "CompanionConfig"),
        ("talk", "TalkSetting"),
    ):
        model = apps.get_model(app_label, model_name)
        model.objects.create(
            name=CONFIG_NAME, **{system_prompt_field(model): system_prompt}
        )
    return {
        **{field: prompt.pk for field, prompt in hn_prompts.items()},
        "companion": system_prompt.pk,
        "talk": system_prompt.pk,
    }


def chosen_prompts(apps) -> dict[str, int]:
    """その時点のモデルで、テスト用の設定が選んでいるプロンプトの pk（`create_configs` と同じ形）."""
    hn_config = apps.get_model("hn_agent", "HNAgentConfig").objects.get(
        name=CONFIG_NAME
    )
    chosen = {field: getattr(hn_config, f"{field}_id") for field in HN_PROMPT_FIELDS}
    for key, (app_label, model_name) in {
        "companion": ("companion", "CompanionConfig"),
        "talk": ("talk", "TalkSetting"),
    }.items():
        model = apps.get_model(app_label, model_name)
        config = model.objects.get(name=CONFIG_NAME)
        chosen[key] = getattr(config, f"{system_prompt_field(model)}_id")
    return chosen


def prompt_rows(apps, names) -> list[tuple]:
    """その時点のモデル（0019 より前）で、プロンプトの行の中身を名前順に読む.

    Returns:
        (pk・名前・Langfuse のプロンプト名・ラベル・フォールバックテキスト・説明) の並び
    """
    return list(
        prompt_model(apps)
        .objects.filter(name__in=names)
        .order_by("name")
        .values_list(
            "pk",
            "name",
            "langfuse_prompt_name",
            "label",
            "fallback_text",
            "description",
        )
    )


def column_names(table: str) -> set[str]:
    """表の列の名前."""
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return {column.name for column in description}

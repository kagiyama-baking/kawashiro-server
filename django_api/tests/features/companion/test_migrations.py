"""companion の migration のテスト（既存の行が移行後にどうなるか）."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from integrations.llm.models import AgentSkill
from tests.fixtures.migrations import applied_apps, prompt_model

BEFORE_RENAME = [("companion", "0001_initial")]
AFTER_RENAME = [("companion", "0002_rename_persona_prompt_ref_to_system_prompt_ref")]
# 旧 CompanionSkill だけがある時点（0003 で AgentSkill を足す前）
BEFORE_AGENT_SKILL = AFTER_RENAME
# AgentSkill を足し、旧 CompanionSkill の行をまだ写していない時点（0004 の前）
BEFORE_SKILL_COPY = [("companion", "0003_agentskill_companionconfig_skills")]
SKILL_COPY = ("companion", "0004_migrate_companionskill_to_agentskill")
AFTER_AGENT_SKILL = [("companion", "0005_delete_companionskill")]

CONFIG_NAME = "companion-migration-test"
OTHER_CONFIG_NAME = "companion-migration-other"
CONFIG_NAMES = (CONFIG_NAME, OTHER_CONFIG_NAME)
PROMPT_REF_NAME = "companion-migration-test-system"
MORNING = "migration-test-morning"
NIGHT = "migration-test-night"
TEST_SKILL_NAMES = (MORNING, NIGHT)
# 後始末で消すスキル名（すべて当て直すと、llm_config の 0015 が名前に接頭辞を付ける）
CLEANUP_SKILL_NAMES = (
    *TEST_SKILL_NAMES,
    *(f"companion-skill-{name}" for name in TEST_SKILL_NAMES),
)
# 規則（companion-skill-<スキル名>）に合わせない参照の識別名と、その Langfuse のプロンプト名
CUSTOM_REF_NAME = "companion-migration-test-custom"
CUSTOM_PROMPT_NAMES = ("custom-night", "custom-morning")
# 後始末で消す参照（llm_config の 0019 の後は、名前が Langfuse のプロンプト名になる）
TEST_REF_NAMES = (
    PROMPT_REF_NAME,
    CUSTOM_REF_NAME,
    *CUSTOM_PROMPT_NAMES,
    *(f"companion-skill-{name}" for name in TEST_SKILL_NAMES),
)

# 収集時（テスト DB を作る前）の接続先。pytest-django は、DB を使うと宣言した
# テスト（django_db マーカーなど）が 1 つも収集されないとテスト DB を作らないので、
# このモジュールだけを実行すると、接続先は開発用の DB（.env の DB_ENGINE、
# 未設定なら db.sqlite3）のままになる。
CONFIGURED_DB_NAME = connection.settings_dict["NAME"]


@pytest.fixture
def migrator(django_db_setup, django_db_blocker):
    """migration を行き来し、後始末ですべて当てた状態に戻して、作った行だけ消す.

    スキーマを変えるので、テストのトランザクションの外で動かす（transactional_db を
    使わない理由は tests/features/talk/test_migrations.py の migrator と同じ）。
    DB の遮断を自分で外すので、テスト DB ができていなければ触る前に中止する。
    後始末では、いま当たっている時点のモデルで作った設定（旧スキル・スキルの選択ごと）と
    参照を先に消してから当て直す。0004 は行き・戻りとも、設定が持つ旧スキル・選んだスキルを
    確かめて止まることがあるため。参照は、llm_config の 0018 が Langfuse のプロンプト名の
    重なりを確かめて止まることがあるため（0004 の止まるテストは、重なる参照を残す）。
    スキルは、すべて当てた後で消す。
    """
    if connection.settings_dict["NAME"] == CONFIGURED_DB_NAME:
        pytest.fail(
            "テスト DB が作られていないので、開発用の DB の migration を動かさないよう"
            "中止します。tests/features/companion/ のように、DB を使うテストと一緒に"
            "実行してください。"
        )
    with django_db_blocker.unblock():
        executor = MigrationExecutor(connection)
        yield executor
        apps = applied_apps(executor)
        apps.get_model("companion", "CompanionConfig").objects.filter(
            name__in=CONFIG_NAMES
        ).delete()
        prompt_model(apps).objects.filter(name__in=TEST_REF_NAMES).delete()
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        AgentSkill.objects.filter(name__in=CLEANUP_SKILL_NAMES).delete()


def _migrate(migrator, targets):
    """targets まで当て（戻し）、その時点のモデルを引ける apps を返す."""
    migrator.loader.build_graph()
    migrator.migrate(targets)
    return migrator.loader.project_state(targets).apps


def _create_config_before_rename(apps) -> int:
    """0001 の時点のモデルで、参照を persona_prompt_ref に持つ設定を作り、参照の pk を返す."""
    prompt_ref = apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.create(name=PROMPT_REF_NAME, langfuse_prompt_name=PROMPT_REF_NAME)
    apps.get_model("companion", "CompanionConfig").objects.create(
        name=CONFIG_NAME, persona_prompt_ref=prompt_ref
    )
    return prompt_ref.pk


def _create_config(apps, name: str = CONFIG_NAME):
    """0002 以降の時点のモデルで、テスト用の設定を作る（システムプロンプトの参照は共有）."""
    prompt_ref, _ = apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.get_or_create(
        name=PROMPT_REF_NAME, defaults={"langfuse_prompt_name": PROMPT_REF_NAME}
    )
    return apps.get_model("companion", "CompanionConfig").objects.create(
        name=name, system_prompt_ref=prompt_ref
    )


def _create_legacy_skill(
    apps,
    config,
    name: str,
    *,
    description: str = "あいさつのときに使う",
    is_enabled: bool = True,
    label: str = "staging",
    ref_name: str | None = None,
    langfuse_prompt_name: str | None = None,
):
    """旧 CompanionSkill を本文の参照ごと作る（参照の名前は、指定しなければ規則どおり）."""
    prompt_name = f"companion-skill-{name}"
    prompt_ref, _ = apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.get_or_create(
        name=ref_name or prompt_name,
        defaults={
            "langfuse_prompt_name": langfuse_prompt_name or prompt_name,
            "label": label,
        },
    )
    return apps.get_model("companion", "CompanionSkill").objects.create(
        config=config,
        name=name,
        description=description,
        is_enabled=is_enabled,
        prompt_ref=prompt_ref,
    )


def _config(apps, name: str = CONFIG_NAME):
    """その時点のモデルで、テスト用に作った設定を読む."""
    return apps.get_model("companion", "CompanionConfig").objects.get(name=name)


@pytest.mark.integration
def test_0002_keeps_prompt_ref_of_existing_config_as_system_prompt_ref(migrator):
    """0001 で作った設定の参照先は、0002 の後も system_prompt_ref として同じまま."""
    prompt_ref_pk = _create_config_before_rename(_migrate(migrator, BEFORE_RENAME))

    new_apps = _migrate(migrator, AFTER_RENAME)

    assert _config(new_apps).system_prompt_ref_id == prompt_ref_pk


@pytest.mark.integration
def test_0002_reverse_restores_prompt_ref_as_persona_prompt_ref(migrator):
    """0001 へ戻すと、参照先は persona_prompt_ref として同じまま戻る."""
    prompt_ref_pk = _create_config_before_rename(_migrate(migrator, BEFORE_RENAME))
    _migrate(migrator, AFTER_RENAME)

    reverted_apps = _migrate(migrator, BEFORE_RENAME)

    assert _config(reverted_apps).persona_prompt_ref_id == prompt_ref_pk


@pytest.mark.integration
def test_0004_copies_legacy_skills_to_agent_skills_with_ref_label(migrator):
    """旧スキルは、名前・説明・有効と、本文の参照のラベルを写した AgentSkill になる."""
    old_apps = _migrate(migrator, BEFORE_AGENT_SKILL)
    config = _create_config(old_apps)
    _create_legacy_skill(old_apps, config, MORNING, description="朝のあいさつ")
    _create_legacy_skill(
        old_apps,
        config,
        NIGHT,
        description="夜のあいさつ",
        is_enabled=False,
        label="production",
    )

    new_apps = _migrate(migrator, AFTER_AGENT_SKILL)

    skills = new_apps.get_model("companion", "AgentSkill").objects.all()
    assert [(s.name, s.description, s.label, s.is_enabled) for s in skills] == [
        (MORNING, "朝のあいさつ", "staging", True),
        (NIGHT, "夜のあいさつ", "production", False),
    ]


@pytest.mark.integration
def test_0004_selects_copied_skills_in_their_config(migrator):
    """写したスキルは、旧スキルが属していた設定で選んだ状態になる."""
    old_apps = _migrate(migrator, BEFORE_AGENT_SKILL)
    config = _create_config(old_apps)
    _create_legacy_skill(old_apps, config, MORNING)
    _create_legacy_skill(old_apps, config, NIGHT, is_enabled=False)

    new_apps = _migrate(migrator, AFTER_AGENT_SKILL)

    assert [s.name for s in _config(new_apps).skills.all()] == [MORNING, NIGHT]


@pytest.mark.integration
def test_0004_keeps_prompt_refs_of_legacy_skills(migrator):
    """旧スキルの本文の参照は消さない（0004 を戻すときに使い直す）."""
    old_apps = _migrate(migrator, BEFORE_AGENT_SKILL)
    legacy = _create_legacy_skill(old_apps, _create_config(old_apps), MORNING)

    new_apps = _migrate(migrator, AFTER_AGENT_SKILL)

    assert (
        new_apps.get_model("langfuse_integration", "LangfusePromptRef")
        .objects.filter(pk=legacy.prompt_ref_id)
        .exists()
    )


@pytest.mark.integration
def test_0004_with_same_skill_in_two_configs_shares_one_agent_skill(migrator):
    """2 つの設定に同じ名前・同じ内容の旧スキルがあれば、1 つのスキルを両方で選ぶ."""
    old_apps = _migrate(migrator, BEFORE_AGENT_SKILL)
    for name in CONFIG_NAMES:
        _create_legacy_skill(old_apps, _create_config(old_apps, name), MORNING)

    new_apps = _migrate(migrator, AFTER_AGENT_SKILL)

    skill = new_apps.get_model("companion", "AgentSkill").objects.get(name=MORNING)
    assert sorted(config.name for config in skill.configs.all()) == sorted(CONFIG_NAMES)


@pytest.mark.integration
def test_0004_with_prompt_name_not_following_rule_stops_and_copies_nothing(migrator):
    """本文の参照の Langfuse プロンプト名が companion-skill-<名前> でなければ止め、何も写さない.

    起動時の migrate が止まる（0004 は当たらない）ので、黙って別の本文を読ませることはない。
    エラーには、直すべきスキル・参照・プロンプト名と、規則どおりの名前を挙げる。
    """
    old_apps = _migrate(migrator, BEFORE_AGENT_SKILL)
    config = _create_config(old_apps)
    _create_legacy_skill(old_apps, config, MORNING)
    _create_legacy_skill(
        old_apps,
        config,
        NIGHT,
        ref_name=CUSTOM_REF_NAME,
        langfuse_prompt_name="custom-night",
    )

    with pytest.raises(RuntimeError) as exc_info:
        _migrate(migrator, AFTER_AGENT_SKILL)

    message = str(exc_info.value)
    for expected in (
        NIGHT,
        CUSTOM_REF_NAME,
        "custom-night",
        f"companion-skill-{NIGHT}",
    ):
        assert expected in message
    assert MORNING not in message
    assert SKILL_COPY not in MigrationRecorder(connection).applied_migrations()
    stopped_apps = migrator.loader.project_state(BEFORE_SKILL_COPY).apps
    assert not stopped_apps.get_model("companion", "AgentSkill").objects.exists()
    assert not _config(stopped_apps).skills.exists()


@pytest.mark.integration
def test_0004_with_same_name_and_different_content_stops(migrator):
    """同じ名前の旧スキルの内容（説明・有効・ラベル）が設定ごとに違えば止める.

    スキル名は全体で一意になるので、どちらかを選んで黙って捨てない。
    """
    old_apps = _migrate(migrator, BEFORE_AGENT_SKILL)
    _create_legacy_skill(old_apps, _create_config(old_apps), MORNING)
    _create_legacy_skill(
        old_apps,
        _create_config(old_apps, OTHER_CONFIG_NAME),
        MORNING,
        label="production",
        ref_name=CUSTOM_REF_NAME,
    )

    with pytest.raises(RuntimeError) as exc_info:
        _migrate(migrator, AFTER_AGENT_SKILL)

    message = str(exc_info.value)
    for expected in (MORNING, CONFIG_NAME, OTHER_CONFIG_NAME):
        assert expected in message
    assert SKILL_COPY not in MigrationRecorder(connection).applied_migrations()


@pytest.mark.integration
def test_0005_reverse_restores_legacy_skills_with_their_prompt_refs(migrator):
    """0002 へ戻すと、旧スキルが元の設定・内容・本文の参照のまま戻る（参照は増えない）."""
    old_apps = _migrate(migrator, BEFORE_AGENT_SKILL)
    config = _create_config(old_apps)
    morning = _create_legacy_skill(old_apps, config, MORNING, description="朝")
    night = _create_legacy_skill(
        old_apps, config, NIGHT, description="夜", is_enabled=False
    )
    ref_count = old_apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.count()
    _migrate(migrator, AFTER_AGENT_SKILL)

    reverted_apps = _migrate(migrator, BEFORE_AGENT_SKILL)

    skills = _config(reverted_apps).skills.order_by("name")
    assert [(s.name, s.description, s.is_enabled, s.prompt_ref_id) for s in skills] == [
        (MORNING, "朝", True, morning.prompt_ref_id),
        (NIGHT, "夜", False, night.prompt_ref_id),
    ]
    assert (
        reverted_apps.get_model(
            "langfuse_integration", "LangfusePromptRef"
        ).objects.count()
        == ref_count
    )


@pytest.mark.integration
def test_0005_reverse_creates_prompt_ref_following_rule_for_new_skill(migrator):
    """0005 の後に登録したスキルも、0003 へ戻すと規則どおりの参照を作って旧スキルに戻る."""
    new_apps = _migrate(migrator, AFTER_AGENT_SKILL)
    config = _create_config(new_apps)
    config.skills.add(
        new_apps.get_model("companion", "AgentSkill").objects.create(
            name=MORNING, description="朝のあいさつ", label="staging"
        )
    )

    reverted_apps = _migrate(migrator, BEFORE_SKILL_COPY)

    legacy = (
        reverted_apps.get_model("companion", "CompanionSkill")
        .objects.select_related("prompt_ref")
        .get(config__name=CONFIG_NAME)
    )
    assert (legacy.name, legacy.description, legacy.is_enabled) == (
        MORNING,
        "朝のあいさつ",
        True,
    )
    prompt_name = f"companion-skill-{MORNING}"
    assert (
        legacy.prompt_ref.name,
        legacy.prompt_ref.langfuse_prompt_name,
        legacy.prompt_ref.label,
    ) == (prompt_name, prompt_name, "staging")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("langfuse_prompt_name", "label"),
    [
        pytest.param("custom-morning", "staging", id="other_prompt_name"),
        pytest.param(f"companion-skill-{MORNING}", "production", id="other_label"),
    ],
)
def test_0004_reverse_with_ref_reading_other_body_stops_and_restores_nothing(
    migrator, langfuse_prompt_name, label
):
    """戻すとき、規則どおりの識別名の参照が別の本文を読むなら止め、何も作り直さない.

    別の本文は、Langfuse プロンプト名かラベルがスキルと違うこと。黙ってその参照で
    旧スキルを作り直すと、戻す前と違う本文を読むようになる。エラーには、直すべき
    スキル・参照と、読む本文の違いを挙げる。
    """
    new_apps = _migrate(migrator, AFTER_AGENT_SKILL)
    agent_skill = new_apps.get_model("companion", "AgentSkill")
    _create_config(new_apps).skills.add(
        agent_skill.objects.create(name=MORNING, description="朝", label="staging"),
        agent_skill.objects.create(name=NIGHT, description="夜", label="staging"),
    )
    refs = new_apps.get_model("langfuse_integration", "LangfusePromptRef").objects
    refs.create(
        name=f"companion-skill-{MORNING}",
        langfuse_prompt_name=langfuse_prompt_name,
        label=label,
    )
    ref_count = refs.count()

    with pytest.raises(RuntimeError) as exc_info:
        _migrate(migrator, BEFORE_SKILL_COPY)

    message = str(exc_info.value)
    for expected in (
        MORNING,
        f"{langfuse_prompt_name}@{label}",
        f"companion-skill-{MORNING}@staging",
    ):
        assert expected in message
    assert NIGHT not in message
    assert SKILL_COPY in MigrationRecorder(connection).applied_migrations()
    stopped_apps = migrator.loader.project_state([SKILL_COPY]).apps
    assert not stopped_apps.get_model("companion", "CompanionSkill").objects.exists()
    assert (
        stopped_apps.get_model(
            "langfuse_integration", "LangfusePromptRef"
        ).objects.count()
        == ref_count
    )


@pytest.mark.integration
def test_0004_round_trip_twice_without_0005_keeps_one_legacy_skill_each(migrator):
    """0005 を当てずに 0004 を 2 回行き来しても、旧スキルは 1 件ずつのまま（内容も参照も同じ）.

    0005 の前は旧スキルの行が残っているので、戻すときは作り直さずに更新する。
    """
    old_apps = _migrate(migrator, BEFORE_SKILL_COPY)
    config = _create_config(old_apps)
    morning = _create_legacy_skill(old_apps, config, MORNING, description="朝")
    night = _create_legacy_skill(
        old_apps, config, NIGHT, description="夜", is_enabled=False
    )

    for _ in range(2):
        _migrate(migrator, [SKILL_COPY])
        reverted_apps = _migrate(migrator, BEFORE_SKILL_COPY)

    skills = (
        reverted_apps.get_model("companion", "CompanionSkill")
        .objects.filter(config__name=CONFIG_NAME)
        .order_by("name")
    )
    assert [(s.name, s.description, s.is_enabled, s.prompt_ref_id) for s in skills] == [
        (MORNING, "朝", True, morning.prompt_ref_id),
        (NIGHT, "夜", False, night.prompt_ref_id),
    ]

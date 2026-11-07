"""talk の migration のテスト（既存の行が移行後にどうなるか）."""

from datetime import UTC, datetime

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

# Talk 設定（0017）より前
BEFORE_TALK_SETTINGS = [("talk", "0016_talkconfig_synthesize_rate_limit")]
# 既存のチャットを Talk 設定へ移す前（0017）と、移す migration（0018）
BEFORE_BIND = [("talk", "0017_talksetting_chatsession_setting_skill")]
AFTER_BIND = [("talk", "0018_bind_chat_sessions_to_talk_settings")]
# 旧会話生成設定（プリセット）の表と、チャットの旧プリセット名の列を消す migration（0019）
AFTER_REMOVE_PRESETS = [
    ("talk", "0019_delete_talkconfig_remove_chatsession_config_name")
]

# 0018・0019 のテストで作るもの（後始末で消す）
BIND_USER_EMAIL = "talk-bind-test@example.com"
BIND_PRESETS = (
    "bind-chat",
    "bind-morning",
    "bind-unused",
    "bind-a",
    "bind-b",
    "bind-c",
)
BIND_REFS = tuple(f"{name}-system" for name in BIND_PRESETS) + ("bind-other-system",)
# 0018 の前にあった時刻（紐づけで変わらないことを確かめる）
OLD_UPDATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

# 収集時（テスト DB を作る前）の接続先。pytest-django は、DB を使うと宣言した
# テスト（django_db マーカーなど）が 1 つも収集されないとテスト DB を作らないので、
# このモジュールだけを実行すると、接続先は開発用の DB（.env の DB_ENGINE、
# 未設定なら db.sqlite3）のままになる。
CONFIGURED_DB_NAME = connection.settings_dict["NAME"]


@pytest.fixture
def migrator(django_db_setup, django_db_blocker):
    """migration を行き来し、後始末ですべて当てた状態に戻して、作った行だけ消す.

    スキーマを変えるので、テストのトランザクションの外で動かす。transactional_db は
    後始末で全テーブルを空にし、data migration で入れた行（HN のプロンプト参照など）
    まで消すので使わない（並び順しだいで、後に流れるテストが落ちる）。
    DB の遮断を自分で外すので、テスト DB ができていなければ触る前に中止する。
    """
    if connection.settings_dict["NAME"] == CONFIGURED_DB_NAME:
        pytest.fail(
            "テスト DB が作られていないので、開発用の DB の migration を動かさないよう"
            "中止します。tests/features/talk/ のように、DB を使うテストと一緒に"
            "実行してください。"
        )
    with django_db_blocker.unblock():
        executor = MigrationExecutor(connection)
        yield executor
        # 0018 が止まる行が残っていると当て直せないので、いま当たっている時点のモデルで先に消す
        _delete_bind_rows(_applied_apps(executor))
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())


def _applied_apps(migrator):
    """DB に当たっている migration の時点のモデルを引ける apps を返す（グラフを読み直す）."""
    migrator.loader.build_graph()
    nodes = migrator.loader.graph.nodes
    applied = [key for key in migrator.loader.applied_migrations if key in nodes]
    return migrator.loader.project_state(applied).apps


def _talk_model(apps, model_name):
    """その時点にある talk のモデルを返す（Talk 設定は 0017 から、プリセットは 0019 の前まで）."""
    try:
        return apps.get_model("talk", model_name)
    except LookupError:
        return None


def _delete_bind_rows(apps):
    """0018・0019 のテストで作った行を消す（ユーザーを消すとチャットも消える）."""
    apps.get_model(settings.AUTH_USER_MODEL).objects.filter(
        email=BIND_USER_EMAIL
    ).delete()
    talk_setting = _talk_model(apps, "TalkSetting")
    if talk_setting is not None:
        talk_setting.objects.filter(system_prompt_ref__name__in=BIND_REFS).delete()
    talk_config = _talk_model(apps, "TalkConfig")
    if talk_config is not None:
        talk_config.objects.filter(name__in=BIND_PRESETS).delete()
    apps.get_model("langfuse_integration", "LangfusePromptRef").objects.filter(
        name__in=BIND_REFS
    ).delete()


def _migrate(migrator, targets):
    """targets まで当て（戻し）、その時点のモデルを引ける apps を返す."""
    migrator.loader.build_graph()
    migrator.migrate(targets)
    return migrator.loader.project_state(targets).apps


def _bind_user(apps) -> int:
    return (
        apps.get_model(settings.AUTH_USER_MODEL)
        .objects.create(email=BIND_USER_EMAIL, name="移行テスト", password="!")
        .pk
    )


def _ref(apps, name):
    return apps.get_model("langfuse_integration", "LangfusePromptRef").objects.create(
        name=name, langfuse_prompt_name=name, fallback_text="移行テストのプロンプト"
    )


def _preset(apps, name, display_name, **tts):
    """プリセット（会話生成設定）を作る（システムプロンプトの参照は `<name>-system`）."""
    ref = _ref(apps, f"{name}-system")
    return apps.get_model("talk", "TalkConfig").objects.create(
        name=name,
        display_name=display_name,
        system_prompt_ref=ref,
        user_prompt_ref=ref,
        **tts,
    )


def _session(apps, user_id, config_name) -> str:
    """旧プリセット名だけを持つチャットを作り、更新日時を 0018 の前の時刻にする."""
    session_model = apps.get_model("talk", "ChatSession")
    session = session_model.objects.create(user_id=user_id, config_name=config_name)
    session_model.objects.filter(pk=session.pk).update(updated_at=OLD_UPDATED_AT)
    return session.pk


def _settings_by_name(apps):
    talk_setting = apps.get_model("talk", "TalkSetting")
    return {
        s.name: s
        for s in talk_setting.objects.filter(system_prompt_ref__name__in=BIND_REFS)
    }


def _table_names() -> set[str]:
    return set(connection.introspection.table_names())


def _column_names(table: str) -> set[str]:
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return {column.name for column in description}


def _bound_session(apps, user_id) -> tuple[str, int]:
    """0018 の後の状態のチャットを作る（旧プリセット名と、移した Talk 設定を持つ）.

    Returns:
        (チャットの pk, Talk 設定の pk)
    """
    preset = _preset(apps, "bind-chat", "チャット用（移行テスト）")
    setting = apps.get_model("talk", "TalkSetting").objects.create(
        name="チャット用（移行テスト）",
        system_prompt_ref_id=preset.system_prompt_ref_id,
    )
    session = _session(apps, user_id, "bind-chat")
    apps.get_model("talk", "ChatSession").objects.filter(pk=session).update(
        setting=setting
    )
    return session, setting.pk


@pytest.mark.integration
def test_0017_lets_code_before_talk_settings_create_sessions(migrator):
    """0017 の後（0019 より前）も、Talk 設定を知らないコード（イメージだけ戻したとき）がチャットを作れる.

    0016 時点のモデルは INSERT に Talk 設定・シーンの列を含めないので、どちらも空（NULL）になる。
    """
    apps = _migrate(migrator, AFTER_BIND)
    old_apps = migrator.loader.project_state(BEFORE_TALK_SETTINGS).apps

    old = old_apps.get_model("talk", "ChatSession").objects.create(
        user_id=_bind_user(apps), config_name="chat"
    )

    session = apps.get_model("talk", "ChatSession").objects.get(pk=old.pk)
    assert (session.setting_id, session.skill_id, session.config_name) == (
        None,
        None,
        "chat",
    )


@pytest.mark.integration
def test_0018_creates_one_setting_per_used_preset_with_same_prompt_and_voice(
    migrator,
):
    """チャットに使われたプリセットごとに、同じシステムプロンプトと音声の Talk 設定を作る.

    名前はプリセットの表示名。有効・シーンなし。使われていないプリセットからは作らない。
    """
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    chat = _preset(
        apps,
        "bind-chat",
        "チャット用（移行テスト）",
        tts_enabled=True,
        tts_model="hiroki",
        tts_style="Happy",
        tts_speed=1.2,
        tts_format="mp3",
    )
    morning = _preset(apps, "bind-morning", "おはよう（移行テスト）")
    _preset(apps, "bind-unused", "使われない（移行テスト）")
    _session(apps, user_id, "bind-chat")
    _session(apps, user_id, "bind-chat")
    _session(apps, user_id, "bind-morning")

    apps = _migrate(migrator, AFTER_BIND)

    settings_by_name = _settings_by_name(apps)
    assert set(settings_by_name) == {
        "チャット用（移行テスト）",
        "おはよう（移行テスト）",
    }
    chat_setting = settings_by_name["チャット用（移行テスト）"]
    assert chat_setting.system_prompt_ref_id == chat.system_prompt_ref_id
    assert (
        chat_setting.tts_enabled,
        chat_setting.tts_model,
        chat_setting.tts_style,
        chat_setting.tts_speed,
        chat_setting.tts_format,
    ) == (True, "hiroki", "Happy", 1.2, "mp3")
    assert chat_setting.is_enabled is True
    assert list(chat_setting.skills.all()) == []
    morning_setting = settings_by_name["おはよう（移行テスト）"]
    assert morning_setting.system_prompt_ref_id == morning.system_prompt_ref_id
    assert morning_setting.tts_enabled is False


@pytest.mark.integration
def test_0018_binds_sessions_to_their_setting_and_keeps_updated_at(migrator):
    """既存のチャットを、プリセットから作った Talk 設定に紐づける（更新日時は変えない）."""
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    _preset(apps, "bind-chat", "チャット用（移行テスト）")
    _preset(apps, "bind-morning", "おはよう（移行テスト）")
    chat_session = _session(apps, user_id, "bind-chat")
    morning_session = _session(apps, user_id, "bind-morning")

    apps = _migrate(migrator, AFTER_BIND)

    sessions = apps.get_model("talk", "ChatSession").objects.select_related("setting")
    by_pk = {s.pk: s for s in sessions.filter(pk__in=[chat_session, morning_session])}
    assert by_pk[chat_session].setting.name == "チャット用（移行テスト）"
    assert by_pk[morning_session].setting.name == "おはよう（移行テスト）"
    assert {s.updated_at for s in by_pk.values()} == {OLD_UPDATED_AT}
    assert {s.skill_id for s in by_pk.values()} == {None}


@pytest.mark.integration
def test_0018_leaves_sessions_of_deleted_preset_unbound(migrator):
    """プリセットが消えたチャットは紐づけない（Talk 設定も作らない）."""
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    orphan = _session(apps, user_id, "bind-gone")

    apps = _migrate(migrator, AFTER_BIND)

    session = apps.get_model("talk", "ChatSession").objects.get(pk=orphan)
    assert (session.setting_id, session.config_name) == (None, "bind-gone")
    assert _settings_by_name(apps) == {}


@pytest.mark.integration
def test_0018_with_shared_display_name_adds_preset_name(migrator):
    """表示名がほかのプリセットと重なるときは、名前に（プリセット名）を付ける."""
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    _preset(apps, "bind-a", "同じ表示名（移行テスト）")
    _preset(apps, "bind-b", "同じ表示名（移行テスト）")
    _preset(apps, "bind-c", "  ")
    _session(apps, user_id, "bind-a")
    _session(apps, user_id, "bind-b")
    _session(apps, user_id, "bind-c")

    apps = _migrate(migrator, AFTER_BIND)

    assert set(_settings_by_name(apps)) == {
        "同じ表示名（移行テスト）（bind-a）",
        "同じ表示名（移行テスト）（bind-b）",
        "bind-c",
    }


@pytest.mark.integration
def test_0018_reuses_setting_with_same_name_and_system_prompt(migrator):
    """同じ名前でシステムプロンプトも同じ Talk 設定があれば、作らずにそれへ紐づける.

    音声の設定は違ってもよい（移した後に admin で調整した設定を、紐づけ直しでも使う）。
    """
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    chat = _preset(apps, "bind-chat", "チャット用（移行テスト）")
    existing = apps.get_model("talk", "TalkSetting").objects.create(
        name="チャット用（移行テスト）",
        system_prompt_ref_id=chat.system_prompt_ref_id,
        tts_enabled=True,
    )
    session = _session(apps, user_id, "bind-chat")

    apps = _migrate(migrator, AFTER_BIND)

    assert list(_settings_by_name(apps)) == ["チャット用（移行テスト）"]
    bound = apps.get_model("talk", "ChatSession").objects.get(pk=session)
    assert bound.setting_id == existing.pk


@pytest.mark.integration
def test_0018_with_same_name_but_other_system_prompt_stops_and_changes_nothing(
    migrator,
):
    """同じ名前で別のシステムプロンプトの Talk 設定があれば、何も変えずに止まる."""
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    _preset(apps, "bind-chat", "チャット用（移行テスト）")
    _preset(apps, "bind-morning", "おはよう（移行テスト）")
    apps.get_model("talk", "TalkSetting").objects.create(
        name="チャット用（移行テスト）",
        system_prompt_ref=_ref(apps, "bind-other-system"),
    )
    chat_session = _session(apps, user_id, "bind-chat")
    morning_session = _session(apps, user_id, "bind-morning")

    migrator.loader.build_graph()
    with pytest.raises(RuntimeError, match="チャット用（移行テスト）") as exc_info:
        migrator.migrate(AFTER_BIND)

    assert "何も変えていません" in str(exc_info.value)
    apps = migrator.loader.project_state(BEFORE_BIND).apps
    assert set(_settings_by_name(apps)) == {"チャット用（移行テスト）"}
    sessions = apps.get_model("talk", "ChatSession").objects.filter(
        pk__in=[chat_session, morning_session]
    )
    assert {s.setting_id for s in sessions} == {None}
    applied = MigrationRecorder(connection).applied_migrations()
    assert AFTER_BIND[0] not in applied


@pytest.mark.integration
def test_0018_with_planned_names_colliding_stops_and_changes_nothing(migrator):
    """プリセットから作る名前どうしが重なるときも、何も変えずに止まる."""
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    # 表示名の重なる 2 件のうち bind-b は「重なる表示名（bind-b）」になり、bind-a の表示名と同じ
    _preset(apps, "bind-a", "重なる表示名（bind-b）")
    _preset(apps, "bind-b", "重なる表示名")
    _preset(apps, "bind-c", "重なる表示名")
    for name in ("bind-a", "bind-b", "bind-c"):
        _session(apps, user_id, name)

    migrator.loader.build_graph()
    with pytest.raises(RuntimeError, match="重なる表示名（bind-b）"):
        migrator.migrate(AFTER_BIND)

    apps = migrator.loader.project_state(BEFORE_BIND).apps
    assert _settings_by_name(apps) == {}


@pytest.mark.integration
def test_0018_round_trip_to_0016_keeps_preset_name_and_binds_again(migrator):
    """0016 まで戻しても旧プリセット名は残り、当て直すと同じように紐づく."""
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    _preset(apps, "bind-chat", "チャット用（移行テスト）")
    session = _session(apps, user_id, "bind-chat")
    _migrate(migrator, AFTER_BIND)

    apps = _migrate(migrator, BEFORE_TALK_SETTINGS)
    old = apps.get_model("talk", "ChatSession").objects.get(pk=session)
    assert old.config_name == "bind-chat"

    apps = _migrate(migrator, AFTER_BIND)
    bound = apps.get_model("talk", "ChatSession").objects.select_related("setting")
    assert bound.get(pk=session).setting.name == "チャット用（移行テスト）"


@pytest.mark.integration
def test_0018_rebinds_to_renamed_setting_already_used_by_same_preset(migrator):
    """紐づけ直しでは、同じプリセットのチャットが紐づく Talk 設定を使う（改名していても作らない）."""
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    _preset(apps, "bind-chat", "チャット用（移行テスト）")
    first = _session(apps, user_id, "bind-chat")
    apps = _migrate(migrator, AFTER_BIND)
    apps.get_model("talk", "TalkSetting").objects.filter(
        name="チャット用（移行テスト）"
    ).update(name="ひな（移行テストで改名）")

    # 旧版のコードが、紐づけの後にチャットを作った
    apps = _migrate(migrator, BEFORE_BIND)
    later = _session(apps, user_id, "bind-chat")
    apps = _migrate(migrator, AFTER_BIND)

    assert list(_settings_by_name(apps)) == ["ひな（移行テストで改名）"]
    sessions = apps.get_model("talk", "ChatSession").objects.select_related("setting")
    assert {sessions.get(pk=pk).setting.name for pk in (first, later)} == {
        "ひな（移行テストで改名）"
    }


@pytest.mark.integration
def test_0018_with_preset_sessions_split_across_settings_stops_and_changes_nothing(
    migrator,
):
    """同じプリセットのチャットが 2 つの Talk 設定に分かれていると、どれに紐づけるか決めずに止まる."""
    apps = _migrate(migrator, BEFORE_BIND)
    user_id = _bind_user(apps)
    chat = _preset(apps, "bind-chat", "チャット用（移行テスト）")
    talk_setting = apps.get_model("talk", "TalkSetting")
    session_model = apps.get_model("talk", "ChatSession")
    for name in ("分かれた設定 A（移行テスト）", "分かれた設定 B（移行テスト）"):
        setting = talk_setting.objects.create(
            name=name, system_prompt_ref_id=chat.system_prompt_ref_id
        )
        session_model.objects.filter(pk=_session(apps, user_id, "bind-chat")).update(
            setting=setting
        )
    unbound = _session(apps, user_id, "bind-chat")

    migrator.loader.build_graph()
    with pytest.raises(RuntimeError, match="bind-chat") as exc_info:
        migrator.migrate(AFTER_BIND)

    assert "何も変えていません" in str(exc_info.value)
    apps = migrator.loader.project_state(BEFORE_BIND).apps
    assert (
        apps.get_model("talk", "ChatSession").objects.get(pk=unbound).setting_id is None
    )
    assert len(_settings_by_name(apps)) == 2


@pytest.mark.integration
def test_0019_drops_presets_table_and_preset_name_column_and_keeps_bound_sessions(
    migrator,
):
    """プリセットの表と旧プリセット名の列を消す（Talk 設定への紐づけと更新日時は残る）.

    プリセットが参照していたプロンプト参照は消さない。
    """
    apps = _migrate(migrator, AFTER_BIND)
    session, setting_id = _bound_session(apps, _bind_user(apps))

    apps = _migrate(migrator, AFTER_REMOVE_PRESETS)

    assert "talk_talkconfig" not in _table_names()
    assert "config_name" not in _column_names("talk_chatsession")
    chat = apps.get_model("talk", "ChatSession").objects.get(pk=session)
    assert (chat.setting_id, chat.updated_at) == (setting_id, OLD_UPDATED_AT)
    refs = apps.get_model("langfuse_integration", "LangfusePromptRef").objects
    assert refs.filter(name="bind-chat-system").exists()


@pytest.mark.integration
def test_0019_backwards_recreates_empty_presets_and_blank_preset_names(migrator):
    """0018 へ戻すと空のプリセットの表と、空文字の旧プリセット名の列ができる（消したものは戻らない）."""
    apps = _migrate(migrator, AFTER_BIND)
    session, setting_id = _bound_session(apps, _bind_user(apps))
    _migrate(migrator, AFTER_REMOVE_PRESETS)

    apps = _migrate(migrator, AFTER_BIND)

    assert "talk_talkconfig" in _table_names()
    assert not apps.get_model("talk", "TalkConfig").objects.exists()
    chat = apps.get_model("talk", "ChatSession").objects.get(pk=session)
    assert (chat.config_name, chat.setting_id) == ("", setting_id)


@pytest.mark.integration
@pytest.mark.django_db
def test_rolling_back_service_display_name_keeps_talk_settings_migrations():
    """サービスの表示名（llm_config 0017）だけを戻しても、Talk 設定と逆参照名の migration は外れない."""
    plan = MigrationExecutor(connection).migration_plan(
        [("llm_config", "0016_alter_llmserviceconfig_options")]
    )

    assert [(migration.app_label, migration.name) for migration, _ in plan] == [
        ("llm_config", "0017_alter_llmserviceconfig_service_name")
    ]

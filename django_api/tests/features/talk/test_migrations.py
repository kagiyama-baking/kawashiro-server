"""talk の migration のテスト（既存の行が移行後にどうなるか）."""

from datetime import UTC, datetime

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

from features.talk.models import ChatSession, TalkConfig
from integrations.langfuse.models import LangfusePromptRef

BEFORE_RATE_LIMIT = [("talk", "0015_chatsession_chatmessage_and_more")]
AFTER_RATE_LIMIT = [("talk", "0016_talkconfig_synthesize_rate_limit")]
# Talk 設定（0017）より前
BEFORE_TALK_SETTINGS = [("talk", "0016_talkconfig_synthesize_rate_limit")]
# 既存のチャットを Talk 設定へ移す前（0017）と、移す migration（0018）
BEFORE_BIND = [("talk", "0017_talksetting_chatsession_setting_skill")]
AFTER_BIND = [("talk", "0018_bind_chat_sessions_to_talk_settings")]

# 0018 のテストで作るもの（後始末で消す）
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

LEGACY_CONFIG_NAME = "legacy"
LEGACY_PROMPT_REF_NAME = "talk-legacy"

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
        TalkConfig.objects.filter(name=LEGACY_CONFIG_NAME).delete()
        LangfusePromptRef.objects.filter(name=LEGACY_PROMPT_REF_NAME).delete()


def _applied_apps(migrator):
    """DB に当たっている migration の時点のモデルを引ける apps を返す（グラフを読み直す）."""
    migrator.loader.build_graph()
    nodes = migrator.loader.graph.nodes
    applied = [key for key in migrator.loader.applied_migrations if key in nodes]
    return migrator.loader.project_state(applied).apps


def _delete_bind_rows(apps):
    """0018 のテストで作った行を消す（ユーザーを消すとチャットも消える）."""
    apps.get_model(settings.AUTH_USER_MODEL).objects.filter(
        email=BIND_USER_EMAIL
    ).delete()
    try:
        talk_setting = apps.get_model("talk", "TalkSetting")
    except LookupError:  # 0017 より前まで戻した
        pass
    else:
        talk_setting.objects.filter(system_prompt_ref__name__in=BIND_REFS).delete()
    apps.get_model("talk", "TalkConfig").objects.filter(name__in=BIND_PRESETS).delete()
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


@pytest.mark.integration
def test_0016_sets_rate_limit_10_on_existing_configs(migrator):
    """移行前からあるプリセットの生成回数の上限は 10 になる."""
    migrator.migrate(BEFORE_RATE_LIMIT)
    old_apps = migrator.loader.project_state(BEFORE_RATE_LIMIT).apps
    prompt_ref = old_apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.create(
        name=LEGACY_PROMPT_REF_NAME,
        langfuse_prompt_name=LEGACY_PROMPT_REF_NAME,
        fallback_text="既存のプロンプト",
    )
    old_apps.get_model("talk", "TalkConfig").objects.create(
        name=LEGACY_CONFIG_NAME,
        display_name="既存のプリセット",
        system_prompt_ref=prompt_ref,
        user_prompt_ref=prompt_ref,
    )

    migrator.loader.build_graph()
    migrator.migrate(AFTER_RATE_LIMIT)

    new_apps = migrator.loader.project_state(AFTER_RATE_LIMIT).apps
    config = new_apps.get_model("talk", "TalkConfig").objects.get(
        name=LEGACY_CONFIG_NAME
    )
    assert config.synthesize_rate_limit == 10


@pytest.mark.integration
@pytest.mark.django_db
def test_0016_lets_code_without_rate_limit_create_configs():
    """0016 の後も、上限の列を知らないコード（イメージだけ戻したとき）がプリセットを作れる.

    0015 時点のモデルは INSERT に上限の列を含めないので、DB の既定値で 10 になる。
    """
    old_apps = MigrationLoader(connection).project_state(BEFORE_RATE_LIMIT).apps
    prompt_ref = old_apps.get_model(
        "langfuse_integration", "LangfusePromptRef"
    ).objects.create(
        name=LEGACY_PROMPT_REF_NAME,
        langfuse_prompt_name=LEGACY_PROMPT_REF_NAME,
        fallback_text="旧版のプロンプト",
    )

    old_apps.get_model("talk", "TalkConfig").objects.create(
        name=LEGACY_CONFIG_NAME,
        display_name="旧版で作ったプリセット",
        system_prompt_ref=prompt_ref,
        user_prompt_ref=prompt_ref,
    )

    assert TalkConfig.objects.get(name=LEGACY_CONFIG_NAME).synthesize_rate_limit == 10


@pytest.mark.integration
@pytest.mark.django_db
def test_0017_lets_code_before_talk_settings_create_sessions(django_user_model):
    """0017 の後も、Talk 設定を知らないコード（イメージだけ戻したとき）がチャットを作れる.

    0016 時点のモデルは INSERT に Talk 設定・シーンの列を含めないので、どちらも空（NULL）になる。
    """
    old_apps = MigrationLoader(connection).project_state(BEFORE_TALK_SETTINGS).apps
    user = django_user_model.objects.create_user(
        email="talk-legacy-session@example.com", password="dummypass1234"
    )

    old = old_apps.get_model("talk", "ChatSession").objects.create(
        user_id=user.pk, config_name="chat"
    )

    session = ChatSession.objects.get(pk=old.pk)
    assert (session.setting, session.skill, session.config_name) == (None, None, "chat")


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

"""プロンプト（Prompt）の名前を Langfuse のプロンプト名にする migration（llm_config 0019）のテスト.

0019 は、名前を Langfuse のプロンプト名そのものにし（2 段で一時の名前を経由する）、
Langfuse のプロンプト名とフォールバックテキストの列を消す。0018 の後に名前にできない行が
できていても、同じ検査で何も変えずに止まる。後退では列を戻し、HN Agent の seed の 4 本を
元の識別名に戻す（100 字を超える名前があれば止まる）。

移設（0018 など）のテストは test_prompt_move_migrations.py、共通の時点とヘルパは
tests/fixtures/prompt_migrations.py、フィクスチャ（`prompt_migrator`）は conftest.py。
"""

import pytest

from integrations.llm.models import Prompt
from tests.fixtures.migrations import applied_apps, prompt_model
from tests.fixtures.prompt_migrations import (
    AFTER_RENAME,
    BEFORE_MOVE,
    BEFORE_RENAME,
    RENAME,
    ROLLBACK,
    TEST_PREFIX,
    applied_migrations,
    chosen_prompts,
    column_names,
    create_configs,
    create_prompt,
    migrate_to,
    names_by_pk,
)

# HN Agent の seed の system プロンプト（0019 より前の識別名 → Langfuse のプロンプト名）
HN_SEED_SYSTEM_NAMES = {
    "hn-agent-orchestrator-system": "hn-agent-orchestrator",
    "hn-agent-detective-system": "hn-agent-detective",
    "hn-agent-devils-advocate-system": "hn-agent-devils-advocate",
    "hn-agent-security-responder-system": "hn-agent-security-responder",
}


@pytest.mark.integration
def test_rename_sets_names_to_langfuse_prompt_names_including_swaps_and_chains(
    prompt_migrator,
):
    """名前を Langfuse のプロンプト名に付け替える（pk はそのまま）.

    名前が入れ替わる 2 件と、つながる 2 件（一方の Langfuse 名が他方の名前）があっても、
    一意の制約に触れずに付け替える。名前と Langfuse のプロンプト名が同じ行は変えない。
    """
    apps = migrate_to(prompt_migrator, BEFORE_MOVE)
    x, y, first, second, same = (
        f"{TEST_PREFIX}{suffix}" for suffix in ("x", "y", "1", "2", "same")
    )
    expected = {
        create_prompt(apps, x, langfuse_prompt_name=y).pk: y,
        create_prompt(apps, y, langfuse_prompt_name=x).pk: x,
        create_prompt(apps, first, langfuse_prompt_name=second).pk: second,
        create_prompt(apps, second, langfuse_prompt_name=f"{TEST_PREFIX}3").pk: (
            f"{TEST_PREFIX}3"
        ),
        create_prompt(apps, same).pk: same,
    }

    new_apps = migrate_to(prompt_migrator, AFTER_RENAME)

    assert names_by_pk(new_apps, expected) == expected


@pytest.mark.integration
def test_rename_keeps_prompts_chosen_by_configs(prompt_migrator):
    """名前を付け替えても、設定は同じプロンプト（pk）を選んでいる."""
    apps = migrate_to(prompt_migrator, BEFORE_MOVE)
    chosen = create_configs(apps)
    prompts = prompt_model(apps).objects
    for pk in set(chosen.values()):
        prompts.filter(pk=pk).update(langfuse_prompt_name=f"{TEST_PREFIX}lf-{pk}")

    new_apps = migrate_to(prompt_migrator, AFTER_RENAME)

    assert chosen_prompts(new_apps) == chosen
    assert names_by_pk(new_apps, chosen.values()) == {
        pk: f"{TEST_PREFIX}lf-{pk}" for pk in chosen.values()
    }


@pytest.fixture
def hn_seed_system_prompts(prompt_migrator) -> dict[int, str]:
    """HN Agent の seed の system プロンプト 4 本（pk → すべて当てた時点の名前）.

    seed は data migration が入れるが、同じワーカーで先に流れた transaction=True のテストが
    DB を空にしていることがある（pytest-django は、DB の印のない migration のテストを最後に
    流す）。なければ同じ名前で作る（seed の代わりなので、後始末では消さない）。
    """
    return {
        Prompt.objects.get_or_create(name=name)[0].pk: name
        for name in HN_SEED_SYSTEM_NAMES.values()
    }


@pytest.mark.integration
def test_rename_gives_hn_seed_system_prompts_their_langfuse_names(
    prompt_migrator, hn_seed_system_prompts
):
    """HN Agent の seed の system プロンプト 4 本は、Langfuse のプロンプト名になる（pk はそのまま）."""
    apps = migrate_to(prompt_migrator, BEFORE_MOVE)
    old_names = {new: old for old, new in HN_SEED_SYSTEM_NAMES.items()}
    assert names_by_pk(apps, hn_seed_system_prompts) == {
        pk: old_names[name] for pk, name in hn_seed_system_prompts.items()
    }

    new_apps = migrate_to(prompt_migrator, AFTER_RENAME)

    assert names_by_pk(new_apps, hn_seed_system_prompts) == hn_seed_system_prompts


@pytest.mark.integration
def test_rename_drops_langfuse_prompt_name_and_fallback_text_columns(prompt_migrator):
    """名前を付け替えた後は、Langfuse のプロンプト名とフォールバックテキストの列がない."""
    migrate_to(prompt_migrator, BEFORE_RENAME)
    table = Prompt._meta.db_table
    assert {"langfuse_prompt_name", "fallback_text"} <= column_names(table)

    migrate_to(prompt_migrator, AFTER_RENAME)

    assert {"langfuse_prompt_name", "fallback_text"}.isdisjoint(column_names(table))


@pytest.mark.integration
def test_rename_with_duplicates_added_after_move_stops_and_keeps_names(prompt_migrator):
    """0018 の後に Langfuse のプロンプト名が重なる行ができていても、0019 も止まり何も変えない."""
    apps = migrate_to(prompt_migrator, BEFORE_RENAME)
    shared = f"{TEST_PREFIX}shared"
    pks = [
        create_prompt(apps, f"{TEST_PREFIX}{suffix}", langfuse_prompt_name=shared).pk
        for suffix in ("a", "b")
    ]

    with pytest.raises(RuntimeError, match="何も変えていません"):
        migrate_to(prompt_migrator, AFTER_RENAME)

    assert RENAME not in applied_migrations()
    stopped_apps = prompt_migrator.loader.project_state(BEFORE_RENAME).apps
    assert names_by_pk(stopped_apps, pks) == {
        pks[0]: f"{TEST_PREFIX}a",
        pks[1]: f"{TEST_PREFIX}b",
    }


@pytest.mark.integration
def test_rename_with_unusable_name_added_after_move_stops_and_keeps_names(
    prompt_migrator,
):
    """0018 の後に名前にできない Langfuse 名（途中の CR）の行ができていても、0019 で止まる."""
    apps = migrate_to(prompt_migrator, BEFORE_RENAME)
    pk = create_prompt(
        apps, f"{TEST_PREFIX}bad", langfuse_prompt_name=f"{TEST_PREFIX}a\rb"
    ).pk

    with pytest.raises(RuntimeError, match=f"{TEST_PREFIX}bad"):
        migrate_to(prompt_migrator, AFTER_RENAME)

    assert RENAME not in applied_migrations()
    stopped_apps = prompt_migrator.loader.project_state(BEFORE_RENAME).apps
    assert names_by_pk(stopped_apps, [pk]) == {pk: f"{TEST_PREFIX}bad"}


@pytest.mark.integration
def test_rename_reverse_restores_columns_and_hn_seed_names(
    prompt_migrator, hn_seed_system_prompts
):
    """戻すと列が戻り（Langfuse のプロンプト名は名前と同じ、フォールバックは空）、HN の seed は元の識別名に戻る."""
    added = Prompt.objects.create(name=f"{TEST_PREFIX}added").pk
    seeds = hn_seed_system_prompts
    old_names = {new: old for old, new in HN_SEED_SYSTEM_NAMES.items()}

    old_apps = migrate_to(prompt_migrator, BEFORE_RENAME)

    rows = prompt_model(old_apps).objects.filter(pk__in=[added, *seeds])
    assert set(
        rows.values_list("pk", "name", "langfuse_prompt_name", "fallback_text")
    ) == {
        (added, f"{TEST_PREFIX}added", f"{TEST_PREFIX}added", ""),
        *((pk, old_names[name], name, "") for pk, name in seeds.items()),
    }


@pytest.fixture
def prompt_with_old_seed_name(prompt_migrator, hn_seed_system_prompts):
    """HN の seed の元の識別名（hn-agent-detective-system）を名前に使うプロンプト（後始末で消す）."""
    prompt = Prompt.objects.create(name="hn-agent-detective-system")
    yield prompt
    prompt_model(applied_apps(prompt_migrator)).objects.filter(pk=prompt.pk).delete()


@pytest.mark.integration
def test_rename_reverse_keeps_seed_name_when_old_name_is_taken(
    prompt_migrator, prompt_with_old_seed_name
):
    """元の識別名がほかのプロンプトに使われていれば、その seed は名前を戻さない（重ならないように）."""
    seed = Prompt.objects.get(name="hn-agent-detective")

    old_apps = migrate_to(prompt_migrator, BEFORE_RENAME)

    assert names_by_pk(old_apps, [seed.pk, prompt_with_old_seed_name.pk]) == {
        seed.pk: "hn-agent-detective",
        prompt_with_old_seed_name.pk: "hn-agent-detective-system",
    }


@pytest.mark.integration
def test_rename_reverse_with_name_over_100_chars_stops_and_keeps_0019_applied(
    prompt_migrator,
):
    """100 字を超える名前があれば、戻さずに止める（0019 より前の名前は 100 字まで）.

    0019 は当たったまま、名前も列もそのまま。エラーには、その名前を挙げる。
    """
    long_name = TEST_PREFIX + "a" * (101 - len(TEST_PREFIX))
    Prompt.objects.create(name=long_name)

    with pytest.raises(RuntimeError) as exc_info:
        migrate_to(prompt_migrator, BEFORE_RENAME)

    assert long_name in str(exc_info.value)
    assert "何も変えていません" in str(exc_info.value)
    assert RENAME in applied_migrations()
    assert Prompt.objects.filter(name=long_name).exists()
    assert "langfuse_prompt_name" not in column_names(Prompt._meta.db_table)


@pytest.mark.integration
def test_rollback_after_rename_returns_converted_names_to_langfuse_integration_model(
    prompt_migrator,
):
    """`migrate llm_config 0017` で、付け替えた名前のまま LangfusePromptRef に戻る.

    Langfuse のプロンプト名は名前と同じ（本文を取る先は変わらない）。seed 以外の元の
    識別名は戻らない。
    """
    apps = migrate_to(prompt_migrator, BEFORE_MOVE)
    pk = create_prompt(
        apps, f"{TEST_PREFIX}old", langfuse_prompt_name=f"{TEST_PREFIX}new"
    ).pk
    migrate_to(prompt_migrator, AFTER_RENAME)

    migrate_to(prompt_migrator, ROLLBACK)

    old_apps = prompt_migrator.loader.project_state(BEFORE_MOVE).apps
    assert (
        prompt_model(old_apps)._meta.label == "langfuse_integration.LangfusePromptRef"
    )
    assert list(
        prompt_model(old_apps)
        .objects.filter(pk=pk)
        .values_list("name", "langfuse_prompt_name")
    ) == [(f"{TEST_PREFIX}new", f"{TEST_PREFIX}new")]

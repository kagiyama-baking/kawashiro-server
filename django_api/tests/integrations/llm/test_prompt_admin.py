"""Prompts（Prompt）の管理画面と、設定がプロンプトを選ぶ欄（autocomplete）のテスト."""

import pytest
from django.urls import NoReverseMatch, reverse

from integrations.llm.models import Prompt
from tests.fixtures.factories import PromptFactory

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


def _page_url(page: str, prompt: Prompt) -> str:
    """Prompts の一覧・追加・変更（prompt の）画面の URL."""
    if page == "change":
        return reverse("admin:llm_config_prompt_change", args=[prompt.pk])
    return reverse(f"admin:llm_config_prompt_{page}")


def _prompt_form_data(**fields) -> dict:
    """Prompts の追加フォームの送信内容."""
    return {
        "name": "companion-system",
        "description": "Companion のシステムプロンプト",
        "label": "staging",
        **fields,
    }


def _content(response) -> str:
    """画面の HTML."""
    return response.content.decode()


@pytest.mark.integration
@pytest.mark.django_db
class TestPromptAdminPages:
    """AI設定 → Prompts の一覧・追加・変更の画面."""

    @pytest.mark.parametrize("page", ["changelist", "add", "change"])
    def test_page_opens(self, admin_site_client, page):
        """一覧・追加・変更の画面を開ける."""
        prompt = PromptFactory(name="companion-system")

        response = admin_site_client.get(_page_url(page, prompt))

        assert response.status_code == 200

    def test_changelist_shows_name_label_and_description_without_langfuse_name(
        self, admin_site_client
    ):
        """一覧には名前・ラベル・説明が並び、Langfuse のプロンプト名の列はない（名前がプロンプト名）."""
        PromptFactory(
            name="companion-system", label="staging", description="Companion 用"
        )

        response = admin_site_client.get(reverse("admin:llm_config_prompt_changelist"))

        content = _content(response)
        assert "companion-system" in content
        assert '<td class="field-label">staging</td>' in content
        assert '<td class="field-description">Companion 用</td>' in content
        assert "field-langfuse_prompt_name" not in content

    def test_changelist_search_matches_description(self, admin_site_client):
        """一覧の検索は説明にも当たる."""
        PromptFactory(name="companion-system", description="朝の声かけ")
        PromptFactory(name="talk-system", description="チャット")

        response = admin_site_client.get(
            reverse("admin:llm_config_prompt_changelist"), {"q": "声かけ"}
        )

        names = [prompt.name for prompt in response.context["cl"].result_list]
        assert names == ["companion-system"]

    def test_change_page_has_name_description_and_label_only(self, admin_site_client):
        """入力するのは名前・説明・ラベルだけ（Langfuse のプロンプト名とフォールバックはない）."""
        prompt = PromptFactory(name="companion-system")

        response = admin_site_client.get(_page_url("change", prompt))

        form = response.context["adminform"].form
        assert set(form.fields) == {"name", "description", "label"}
        assert '<textarea name="description"' not in _content(response)

    def test_add_page_explains_body_is_same_named_prompt_without_fallback(
        self, admin_site_client
    ):
        """追加画面の説明に、本文は同じ名前の Langfuse の text プロンプトで、フォールバックはないと出す."""
        response = admin_site_client.get(reverse("admin:llm_config_prompt_add"))

        content = _content(response)
        assert "プロンプト名と同じ名前の Langfuse の text プロンプト" in content
        assert "フォールバックはありません" in content

    def test_add_with_valid_values_creates_prompt(self, admin_site_client):
        """追加画面から、名前・説明・ラベルを入れてプロンプトを登録できる."""
        response = admin_site_client.post(
            reverse("admin:llm_config_prompt_add"), _prompt_form_data()
        )

        assert response.status_code == 302
        prompt = Prompt.objects.get(name="companion-system")
        assert (prompt.description, prompt.label) == (
            "Companion のシステムプロンプト",
            "staging",
        )

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("hn-agent-orchestrator", id="registered"),
            pytest.param("a" * 201, id="201_chars"),
        ],
    )
    def test_add_with_invalid_name_shows_error_and_saves_nothing(
        self, admin_site_client, name
    ):
        """登録済みの名前（HN Agent の seed など）・200 字を超える名前で追加すると、名前のエラーを表示して保存しない.

        前後の空白と改行は、入力欄が保存の前に取り除く。
        """
        before = Prompt.objects.count()

        response = admin_site_client.post(
            reverse("admin:llm_config_prompt_add"), _prompt_form_data(name=name)
        )

        assert response.status_code == 200
        assert "name" in response.context["adminform"].form.errors
        assert Prompt.objects.count() == before

    def test_old_langfuse_prompt_ref_admin_is_gone(self):
        """以前の「Langfuse → Langfuseプロンプト参照」の画面はない."""
        with pytest.raises(NoReverseMatch):
            reverse("admin:langfuse_integration_langfusepromptref_changelist")


@pytest.mark.integration
@pytest.mark.django_db
class TestPromptAutocomplete:
    """設定（HN Agent・Companion・Talk）のプロンプトの欄は、Prompts を検索して選ぶ."""

    @pytest.mark.parametrize(
        ("app_label", "model_name", "field_name"),
        [
            *(("hn_agent", "hnagentconfig", field) for field in HN_PROMPT_FIELDS),
            ("companion", "companionconfig", "system_prompt"),
            ("talk", "talksetting", "system_prompt"),
        ],
    )
    def test_autocomplete_returns_prompts_matching_term(
        self, admin_site_client, app_label, model_name, field_name
    ):
        """検索欄に打った語で、名前が合うプロンプトだけが候補に出る."""
        prompt = PromptFactory(name="companion-system")
        PromptFactory(name="talk-system")

        response = admin_site_client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": app_label,
                "model_name": model_name,
                "field_name": field_name,
                "term": "companion",
            },
        )

        assert response.status_code == 200
        assert [result["id"] for result in response.json()["results"]] == [
            str(prompt.pk)
        ]
